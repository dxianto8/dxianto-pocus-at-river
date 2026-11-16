"""
What happens around an event besides saving it: the history line, the starting checklist,
and the emails. Views and the admin both go through here so the two sides stay in step.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import Activity, Booking, ChecklistItem, CustomerProfile, VenueSettings

logger = logging.getLogger(__name__)

# (title, days before the event it should be done by)
STARTING_CHECKLIST = {
    Booking.EventType.WEDDING: [
        ("Walk through the space with the venue team", 150),
        ("Agree the proposal and sign the rental agreement", 120),
        ("Book your caterer and share their details", 90),
        ("Book music, photography and flowers", 90),
        ("Send invitations", 60),
        ("Share your floor plan and seating", 30),
        ("Confirm the final guest count", 14),
        ("Send the day-of schedule and vendor arrival times", 7),
    ],
    Booking.EventType.CORPORATE: [
        ("Agree the proposal and sign the rental agreement", 60),
        ("Confirm the room layout and equipment you need", 30),
        ("Book catering and share dietary requirements", 21),
        ("Send invitations or the staff announcement", 21),
        ("Confirm the final headcount", 7),
        ("Send the agenda and arrival times", 3),
    ],
    Booking.EventType.OTHER: [
        ("Walk through the space with the venue team", 60),
        ("Agree the proposal and sign the rental agreement", 45),
        ("Book food, drinks and music", 30),
        ("Send invitations", 30),
        ("Confirm the final guest count", 7),
        ("Send the day-of schedule", 3),
    ],
}


def log(booking: Booking, text: str) -> None:
    Activity.objects.create(booking=booking, text=text[:200])


def seed_checklist(booking: Booking) -> None:
    """Give a new request a starting checklist. Steps that would already be overdue get no date."""
    today = timezone.localdate()
    items = []
    for title, days_before in STARTING_CHECKLIST.get(booking.event_type, []):
        due = booking.event_date - timedelta(days=days_before)
        items.append(
            ChecklistItem(booking=booking, title=title, due_date=due if due >= today else None)
        )
    ChecklistItem.objects.bulk_create(items)


def shift_checklist(booking: Booking, old_date) -> None:
    """Move open checklist dates along when the event date changes."""
    delta = booking.event_date - old_date
    today = timezone.localdate()
    for item in booking.checklist.filter(done_at=None, due_date__isnull=False):
        item.due_date = max(item.due_date + delta, today)
        item.save(update_fields=["due_date"])


def profile_for(user) -> CustomerProfile:
    return CustomerProfile.objects.get_or_create(user=user)[0]


def _venue() -> VenueSettings:
    return VenueSettings.objects.filter(pk=1).first() or VenueSettings(pk=1)


def _send(subject: str, body: str, to: str | None) -> None:
    """Email is a courtesy on top of the workspace, so a mail problem never breaks a request."""
    if not to:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # noqa: BLE001 - any mail failure (no SMTP configured, timeout) is non-fatal
        logger.warning("Could not send %r to %s", subject, to, exc_info=True)


def _event_url(request, booking: Booking, name="accounts:booking_detail") -> str:
    path = reverse(name, args=[booking.pk])
    return request.build_absolute_uri(path) if request else path


def _label(booking: Booking) -> str:
    return f"{booking.get_event_type_display()} on {booking.event_date:%B %-d, %Y}"


def notify_customer(booking: Booking, subject: str, lines: list[str], request=None) -> None:
    owner = booking.owner
    if owner is None or not owner.email or not profile_for(owner).email_updates:
        return
    venue = _venue()
    body = "\n\n".join(
        [
            f"Hello {owner.first_name or owner.username},",
            *lines,
            f"Open your event: {_event_url(request, booking)}",
            venue.name,
        ]
    )
    _send(f"{subject} | {venue.name}", body, owner.email)


def notify_venue(booking: Booking, subject: str, lines: list[str], request=None) -> None:
    venue = _venue()
    admin_path = reverse("admin:bookings_booking_change", args=[booking.pk])
    admin_url = request.build_absolute_uri(admin_path) if request else admin_path
    body = "\n\n".join(
        [f"{booking.name} ({booking.email}), {_label(booking)}.", *lines, f"Admin: {admin_url}"]
    )
    _send(subject, body, venue.contact_email)


STATUS_MAIL = {
    Booking.Status.CONFIRMED: "Your event is confirmed",
    Booking.Status.DECLINED: "An update on your event request",
    Booking.Status.CANCELLED: "Your event has been cancelled",
    Booking.Status.PENDING: "Your event request is back in review",
}


def status_changed(booking: Booking, *, by_staff: bool, request=None) -> None:
    """Record a status change and tell the other side."""
    who = "The venue" if by_staff else "You"
    verb = {
        Booking.Status.CONFIRMED: "confirmed the booking",
        Booking.Status.DECLINED: "declined the request",
        Booking.Status.CANCELLED: "cancelled the event",
        Booking.Status.PENDING: "put the request back in review",
    }.get(booking.status)
    if verb is None:
        return
    log(booking, f"{who} {verb}.")
    if by_staff:
        notify_customer(
            booking,
            STATUS_MAIL[booking.status],
            [f"Your {_label(booking)}: {booking.status_description}"],
            request,
        )
    else:
        notify_venue(
            booking,
            f"Cancelled by customer: {_label(booking)}",
            ["The customer cancelled this event in their workspace. The date is free again."],
            request,
        )
