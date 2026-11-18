from datetime import date, timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from . import services
from .calendar import DayState, Month, add_months, bookable_range, build_month, parse_month
from .forms import BookingRequestForm
from .models import HALVES, Booking, EventPackage

TAKEN_MESSAGE = "Sorry, that date was just taken by another request. Please choose another date."


def safe_parse_date(value: str | None) -> date | None:
    try:
        return parse_date(value or "")
    except ValueError:  # well-formed but impossible, e.g. 2026-02-30
        return None


def public_month(month_param: str | None, today: date) -> Month:
    first = parse_month(month_param, today=today)
    start, end = first - timedelta(days=7), add_months(first, 1) + timedelta(days=7)
    return build_month(
        first,
        today=today,
        taken=Booking.objects.public_states(start, end),
        halves=Booking.objects.public_halves(start, end),
    )


def state_of(day: date, month: Month) -> DayState | None:
    for week in month.weeks:
        for cell in week:
            if cell.date == day and cell.in_month:
                return cell.state
    return None


def layout_for(request) -> str:
    """Account holders see the workspace around the page; visitors see the public site."""
    return "accounts/workspace_base.html" if request.user.is_authenticated else "base.html"


@never_cache
@require_http_methods(["GET", "POST"])
def book(request: HttpRequest) -> HttpResponse:
    """Request a date. Open to everyone: an account is optional, email and phone are not."""
    today = timezone.localdate()
    user = request.user if request.user.is_authenticated else None

    if request.method == "POST":
        form = BookingRequestForm(request.POST, user=user)
        if form.is_valid():
            if form.is_spam:  # pretend it worked, save nothing
                return redirect("bookings:requested")
            try:
                with transaction.atomic():
                    booking = form.save()
            except IntegrityError:  # someone else took the date between our check and the insert
                form.add_error("session", TAKEN_MESSAGE)
            else:
                return after_request(request, booking)
        selected = safe_parse_date(request.POST.get("event_date"))
        picked = request.POST.get("session")
    else:
        selected = safe_parse_date(request.GET.get("date"))
        picked = request.GET.get("session")
        form = None

    month_param = request.GET.get("month") or (f"{selected:%Y-%m}" if selected else None)
    month = public_month(month_param, today)
    selected_state = state_of(selected, month) if selected else None
    open_sessions = Booking.objects.open_sessions(selected) if selected else []
    if picked not in open_sessions:  # no choice yet, or that part was taken meanwhile
        picked = open_sessions[0] if open_sessions else None
    if form is None and selected_state is not None and selected_state.is_bookable:
        initial = {"event_date": selected, "session": picked}
        package = (
            EventPackage.objects.published().filter(slug=request.GET.get("package", "")).first()
        )
        if package:
            initial.update(package=package, event_type=package.event_type)
        form = BookingRequestForm(initial=initial, user=user)

    grid = [week[0].date for week in month.weeks] + [month.weeks[-1][-1].date]
    mine: dict = {}  # {date: {"am": booking, "pm": booking}} for the customer's own halves
    if user:
        for b in Booking.objects.active().filter(owner=user, event_date__range=(grid[0], grid[-1])):
            for half in HALVES[b.session]:
                mine.setdefault(b.event_date, {})[half] = b
    first_month, last_day = bookable_range(today)
    jump = []
    cursor = first_month.replace(day=1)
    while cursor <= last_day:
        jump.append(cursor)
        cursor = add_months(cursor, 1)
    return render(
        request,
        "bookings/book.html",
        {
            "month": month,
            "form": form,
            "selected": selected,
            "selected_state": selected_state,
            "selected_session": picked,
            "other_sessions": [s for s in open_sessions if s != picked],
            "mine": mine,
            "jump": jump,
            "package_slug": request.GET.get("package", ""),
            "layout_template": layout_for(request),
        },
    )


def after_request(request: HttpRequest, booking: Booking) -> HttpResponse:
    """Everything that follows a new request, then the next page for the visitor."""
    services.seed_checklist(booking)
    services.log(booking, "You requested this date.")
    services.notify_venue(
        booking,
        f"New request: {booking.name}, {booking.event_date:%B %-d, %Y} "
        f"({booking.get_session_display()})",
        [
            line
            for line in [
                f"{booking.guest_count} guests. Phone: {booking.phone}.",
                "Made without an account." if booking.owner_id is None else "",
                "Wants to order catering." if booking.catering_interest else "",
                booking.message or "No notes.",
            ]
            if line
        ],
        request,
    )
    if booking.owner_id is None:
        services.remember_guest_booking(request, booking)
        services.notify_customer(
            booking,
            "We received your request",
            [
                f"{booking.when} is on hold for you while the venue team reviews your request.",
                "It is not confirmed yet, and nothing has been charged. "
                "We will reply at this email address or call you.",
            ],
            request,
        )
    elif not services.profile_for(request.user).phone:
        profile = services.profile_for(request.user)
        profile.phone = booking.phone
        profile.save(update_fields=["phone"])
    query = urlencode({"booking": booking.pk})
    if booking.catering_interest:
        return redirect(f"{reverse('catering_order')}?{query}")
    return redirect(f"{reverse('bookings:requested')}?{query}")


@never_cache
@require_GET
def requested(request: HttpRequest) -> HttpResponse:
    booking = None
    if request.GET.get("booking"):
        try:
            pk = UUID(request.GET["booking"])
        except ValueError:
            raise Http404 from None
        booking = get_object_or_404(Booking, pk=pk)
        if not services.can_view_booking(request, booking):
            raise Http404
    return render(
        request,
        "bookings/requested.html",
        {
            "booking": booking,
            "day": booking.event_date if booking else None,
            "layout_template": layout_for(request),
            "orders": booking.catering_orders.all() if booking else [],
        },
    )
