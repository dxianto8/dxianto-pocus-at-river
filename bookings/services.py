"""
What happens around an event besides saving it: the history line, the starting checklist,
and the emails. Views and the admin both go through here so the two sides stay in step.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
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
    return (
        f"{booking.get_event_type_display()} on {booking.event_date:%B %-d, %Y} "
        f"({booking.get_session_display()})"
    )


def notify_customer(booking: Booking, subject: str, lines: list[str], request=None) -> None:
    """
    Email the customer. Account holders get a link to their workspace and can turn emails off.
    Guests (requests made without an account) are written to at the email on the request.
    """
    owner = booking.owner
    venue = _venue()
    if owner is None:
        if not booking.email:
            return
        greeting, to = f"Hello {booking.name},", booking.email
        footer = f"Questions? Reply to {venue.contact_email}" + (
            f" or call {venue.phone}." if venue.phone else "."
        )
    else:
        if not owner.email or not profile_for(owner).email_updates:
            return
        greeting, to = f"Hello {owner.first_name or owner.username},", owner.email
        footer = f"Open your event: {_event_url(request, booking)}"
    body = "\n\n".join([greeting, *lines, footer, venue.name])
    _send(f"{subject} | {venue.name}", body, to)


GUEST_SESSION_KEY = "guest_bookings"


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


def notify_appointment(appointment, subject, request=None):
    profile = profile_for(appointment.owner)
    slot = appointment.slot
    url = reverse("accounts:walkthroughs")
    link = request.build_absolute_uri(url) if request else settings.SITE_URL + url
    body = (
        f"{subject}: {timezone.localtime(slot.starts_at):%A, %B %d, %Y at %I:%M %p} "
        f"(Chicago time). Status: {appointment.get_status_display()}.\n\n{link}"
    )
    if profile.email_updates:
        _send(f"{subject} | Pocus at River", body, appointment.owner.email)
    _send(
        f"{subject} | Pocus at River",
        body + f"\nCustomer: {appointment.owner.get_full_name() or appointment.owner.username}",
        _venue().contact_email,
    )


# Requests made without an account ------------------------------------------------------------
#
# The browser session that made a guest request may look at it again (the confirmation page,
# the catering order) and, if that person then signs up or signs in, the request becomes theirs.
# Nothing is ever matched by email address: only the session that created it can claim it.


def remember_guest_booking(request, booking: Booking) -> None:
    ids = [i for i in request.session.get(GUEST_SESSION_KEY, []) if i != str(booking.pk)]
    request.session[GUEST_SESSION_KEY] = [*ids, str(booking.pk)][-10:]


def can_view_booking(request, booking: Booking) -> bool:
    if request.user.is_authenticated and booking.owner_id == request.user.pk:
        return True
    return booking.owner_id is None and str(booking.pk) in request.session.get(
        GUEST_SESSION_KEY, []
    )


def claim_guest_bookings(request, user) -> int:
    """Give the person who just signed in the requests they made earlier in this session."""
    from .models import CateringOrder

    ids = request.session.pop(GUEST_SESSION_KEY, [])
    order_ids = request.session.pop("guest_catering_orders", [])
    if not ids and not order_ids:
        return 0
    claimed = Booking.objects.filter(pk__in=ids, owner__isnull=True).update(owner=user)
    CateringOrder.objects.filter(
        Q(booking__in=ids) | Q(pk__in=order_ids), owner__isnull=True
    ).update(owner=user)
    return claimed


def notify_catering_order(order, request=None) -> None:
    """Tell the venue about a new catering order, and send the customer a receipt."""
    venue = _venue()
    lines = [
        f"{line.quantity} × {line.title}"
        + (f" at ${line.unit_price:,.2f}" if line.unit_price is not None else " (to be quoted)")
        + (f" {line.price_note}" if line.price_note else "")
        for line in order.lines.all()
    ]
    summary = [
        f"For {order.event_date:%A, %B %-d, %Y}"
        + (f" ({order.booking.get_session_display()})" if order.booking_id else "")
        + (f", {order.guest_count} guests." if order.guest_count else "."),
        *lines,
        f"Estimated total: {order.total_display}",
        f"Notes: {order.notes}" if order.notes else "",
    ]
    admin_path = reverse("admin:bookings_cateringorder_change", args=[order.pk])
    admin_url = request.build_absolute_uri(admin_path) if request else admin_path
    _send(
        f"New catering order: {order.name}, {order.event_date:%B %-d, %Y}",
        "\n\n".join(
            [f"{order.name} ({order.email}, {order.phone})", *filter(None, summary), admin_url]
        ),
        venue.contact_email,
    )
    if order.owner_id and not profile_for(order.owner).email_updates:
        return
    _send(
        f"Your catering order | {venue.name}",
        "\n\n".join(
            [
                f"Hello {order.name},",
                "Thank you for your catering order. Here is what you asked for:",
                *filter(None, summary),
                "Nothing has been charged. The venue team will confirm your order, "
                "the final price and how to pay.",
                venue.name,
            ]
        ),
        order.email,
    )
