"""Opt-in reminders. Queue keys prevent repeats; delivery rechecks current ownership and state."""

import base64
import hashlib
import hmac
import json
from datetime import datetime, time, timedelta
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Booking, CustomerProfile, ScheduledNotification, WalkthroughAppointment
from .offering_views import award_loyalty, venue_config
from .services import profile_for


def send_sms(number, body):
    if not all(
        [settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER]
    ):
        raise RuntimeError("Texting is not configured.")
    auth = base64.b64encode(
        f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    ).decode()
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
        data=urlencode({"To": number, "From": settings.TWILIO_FROM_NUMBER, "Body": body}).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise RuntimeError("The texting provider did not accept the message.")
        return json.load(response).get("sid", "")


def morning(day):
    return timezone.make_aware(datetime.combine(day, time(8)), timezone.get_default_timezone())


def queue_notifications(now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    venue = venue_config()
    # A bounded catch-up window avoids mailing historical events when automation is first enabled.
    earliest = today - timedelta(days=2)
    latest = today + timedelta(days=max(venue.reminder_days, venue.feedback_delay_days) + 1)
    for booking in Booking.objects.filter(
        status="confirmed",
        owner__isnull=False,
        event_date__range=(earliest - timedelta(days=venue.feedback_delay_days), latest),
    ).select_related("owner"):
        targets = [
            ("event", booking.event_date - timedelta(days=venue.reminder_days)),
            ("feedback", booking.event_date + timedelta(days=venue.feedback_delay_days)),
        ]
        for kind, day in targets:
            if not earliest <= day <= today:
                continue
            if kind == "feedback" and booking.event_date >= today:
                continue
            enqueue(
                booking.owner,
                kind,
                morning(day),
                booking.event_date,
                booking=booking,
                now=now,
                venue=venue,
            )
    for appointment in WalkthroughAppointment.objects.filter(
        status="confirmed",
        slot__starts_at__gt=now,
        slot__starts_at__lt=now + timedelta(days=venue.reminder_days + 1),
    ).select_related("owner", "slot"):
        date = timezone.localdate(appointment.slot.starts_at)
        day = date - timedelta(days=venue.reminder_days)
        if earliest <= day <= today:
            enqueue(
                appointment.owner,
                "walkthrough",
                morning(day),
                date,
                appointment=appointment,
                now=now,
                venue=venue,
            )


def enqueue(owner, kind, scheduled, reference_date, *, booking=None, appointment=None, now, venue):
    profile = profile_for(owner)
    if kind == "feedback" and not profile.feedback_updates:
        return
    for channel in ("email", "sms"):
        enabled = (
            venue.automated_email_enabled and profile.email_updates
            if channel == "email"
            else venue.automated_sms_enabled and profile.sms_reminders
        )
        if not enabled:
            continue
        target = f"booking:{booking.pk}" if booking else f"visit:{appointment.pk}"
        # Feedback is once per completed event; reminders follow the current event/appointment date.
        key = f"{target}:{owner.pk}:{kind}:{channel}" + (
            f":{reference_date}" if kind != "feedback" else ""
        )
        ScheduledNotification.objects.get_or_create(
            key=key,
            defaults={
                "owner": owner,
                "booking": booking,
                "appointment": appointment,
                "kind": kind,
                "channel": channel,
                "reference_date": reference_date,
                "scheduled_for": scheduled,
            },
        )


def eligible(notification, now):
    profile = profile_for(notification.owner)
    venue = venue_config()
    if notification.kind == "feedback" and not profile.feedback_updates:
        return False
    if notification.channel == "email" and not (
        venue.automated_email_enabled and profile.email_updates and notification.owner.email
    ):
        return False
    if notification.channel == "sms" and not (
        venue.automated_sms_enabled and profile.sms_reminders and profile.phone
    ):
        return False
    if notification.booking_id:
        booking = notification.booking
        if (
            booking.owner_id != notification.owner_id
            or booking.status != "confirmed"
            or booking.event_date != notification.reference_date
        ):
            return False
        today = timezone.localdate(now)
        if notification.kind == "event" and booking.start_time:
            starts_at = timezone.make_aware(
                datetime.combine(booking.event_date, booking.start_time)
            )
            if starts_at <= now:
                return False
        return (
            booking.event_date < today
            if notification.kind == "feedback"
            else booking.event_date >= today
        )
    appointment = notification.appointment
    return bool(
        appointment
        and appointment.owner_id == notification.owner_id
        and appointment.status == "confirmed"
        and appointment.slot.starts_at > now
        and timezone.localdate(appointment.slot.starts_at) == notification.reference_date
    )


def notification_text(notification):
    if notification.kind == "feedback":
        path = reverse("accounts:feedback", args=[notification.booking_id])
        return (
            "How was your event?",
            (
                "Thank you for gathering at Pocus at River. Share feedback about your event "
                f"on {notification.reference_date:%B %d, %Y}. {settings.SITE_URL}{path}"
            ),
        )
    if notification.kind == "walkthrough":
        start = timezone.localtime(notification.appointment.slot.starts_at)
        path = reverse("accounts:walkthroughs")
        return (
            "Your walkthrough appointment",
            (
                f"Your walkthrough at Pocus at River is {start:%A, %B %d at %I:%M %p} "
                f"(Chicago time). {settings.SITE_URL}{path}"
            ),
        )
    booking = notification.booking
    timing = f" at {booking.start_time:%I:%M %p} (Chicago time)" if booking.start_time else ""
    path = reverse("accounts:booking_detail", args=[booking.pk])
    return (
        "Your event is coming up",
        (
            f"Your {booking.get_event_type_display().lower()} at Pocus at River is "
            f"{booking.event_date:%A, %B %d}{timing}. {settings.SITE_URL}{path}"
        ),
    )


def dispatch_notifications(now=None):
    now = now or timezone.now()
    award_loyalty()
    queue_notifications(now)
    sent = failed = skipped = 0
    started = monotonic()
    pending = (
        ScheduledNotification.objects.filter(
            status__in=["queued", "failed"],
            attempts__lt=3,
            scheduled_for__lte=now,
        )
        .filter(Q(last_attempt_at=None) | Q(last_attempt_at__lte=now - timedelta(minutes=5)))
        .select_related("owner", "booking", "appointment__slot")[:100]
    )
    for notification in pending:
        if monotonic() - started > 20:
            break
        # Atomic claim prevents overlapping cron invocations from delivering the same row.
        claimed = ScheduledNotification.objects.filter(
            pk=notification.pk, status=notification.status, attempts=notification.attempts
        ).update(status="sending", attempts=notification.attempts + 1, last_attempt_at=now)
        if not claimed:
            continue
        if notification.scheduled_for < now - timedelta(days=3) or not eligible(notification, now):
            notification.status = "skipped"
            skipped += 1
        else:
            subject, body = notification_text(notification)
            try:
                if notification.channel == "email":
                    if not send_mail(
                        f"{subject} | Pocus at River",
                        body,
                        settings.DEFAULT_FROM_EMAIL,
                        [notification.owner.email],
                    ):
                        raise RuntimeError("Email was not accepted.")
                else:
                    notification.provider_id = send_sms(
                        profile_for(notification.owner).phone, body + " Reply STOP to opt out."
                    )
            except Exception:  # Provider outages must not stop delivery of the remaining queue.
                notification.status = "failed"
                notification.last_error = (
                    "Provider delivery failed. Check provider configuration and logs."
                )
                failed += 1
            else:
                notification.status = "sent"
                notification.sent_at = now
                notification.last_error = ""
                sent += 1
        notification.save(update_fields=["status", "provider_id", "last_error", "sent_at"])
    return {"sent": sent, "failed": failed, "skipped": skipped}


@never_cache
@require_GET
def cron_dispatch(request):
    expected = settings.CRON_SECRET
    supplied = request.headers.get("Authorization", "")
    if not expected or not hmac.compare_digest(supplied, f"Bearer {expected}"):
        return HttpResponse(status=403)
    return JsonResponse(dispatch_notifications())


@csrf_exempt
@require_POST
def sms_opt_out(request):
    # Twilio signs the exact externally visible URL and sorted form parameters.
    token = settings.TWILIO_AUTH_TOKEN
    value = request.build_absolute_uri() + "".join(
        key + request.POST[key] for key in sorted(request.POST)
    )
    expected = base64.b64encode(
        hmac.new(token.encode(), value.encode(), hashlib.sha1).digest()
    ).decode()
    if not token or not hmac.compare_digest(
        expected, request.headers.get("X-Twilio-Signature", "")
    ):
        return HttpResponse(status=403)
    if request.POST.get("Body", "").strip().upper() in {
        "STOP",
        "STOPALL",
        "UNSUBSCRIBE",
        "CANCEL",
        "END",
        "QUIT",
    }:
        CustomerProfile.objects.filter(phone=request.POST.get("From", "")).update(
            sms_reminders=False
        )
    return HttpResponse("<Response></Response>", content_type="application/xml")
