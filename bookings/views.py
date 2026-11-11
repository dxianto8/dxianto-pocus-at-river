from datetime import date, timedelta
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .calendar import DayState, Month, add_months, build_month, parse_month
from .forms import BookingRequestForm
from .models import Booking, EventPackage

TAKEN_MESSAGE = "Sorry, that date was just taken by another request. Please choose another date."


def safe_parse_date(value: str | None) -> date | None:
    try:
        return parse_date(value or "")
    except ValueError:  # well-formed but impossible, e.g. 2026-02-30
        return None


def public_month(month_param: str | None, today: date) -> Month:
    first = parse_month(month_param, today=today)
    taken = Booking.objects.public_states(
        first - timedelta(days=7), add_months(first, 1) + timedelta(days=7)
    )
    return build_month(first, today=today, taken=taken)


def state_of(day: date, month: Month) -> DayState | None:
    for week in month.weeks:
        for cell in week:
            if cell.date == day and cell.in_month:
                return cell.state
    return None


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def book(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()

    if request.method == "POST":
        form = BookingRequestForm(request.POST, user=request.user)
        if form.is_valid():
            if form.is_spam:  # pretend it worked, save nothing
                return redirect("bookings:requested")
            try:
                with transaction.atomic():
                    booking = form.save()
            except IntegrityError:  # someone else took the date between our check and the insert
                form.add_error("event_date", TAKEN_MESSAGE)
            else:
                return redirect(
                    f"{reverse('bookings:requested')}?{urlencode({'booking': booking.pk})}"
                )
        selected = safe_parse_date(request.POST.get("event_date"))
    else:
        selected = safe_parse_date(request.GET.get("date"))
        form = None

    month_param = request.GET.get("month") or (f"{selected:%Y-%m}" if selected else None)
    month = public_month(month_param, today)
    selected_state = state_of(selected, month) if selected else None
    if form is None and selected_state is DayState.AVAILABLE:
        initial = {"event_date": selected}
        package = EventPackage.objects.filter(
            is_published=True, slug=request.GET.get("package", "")
        ).first()
        if package:
            initial.update(package=package, event_type=package.event_type)
        form = BookingRequestForm(initial=initial, user=request.user)

    return render(
        request,
        "bookings/book.html",
        {"month": month, "form": form, "selected": selected, "selected_state": selected_state},
    )


@never_cache
@login_required
@require_GET
def requested(request: HttpRequest) -> HttpResponse:
    booking = None
    if request.GET.get("booking"):
        try:
            pk = UUID(request.GET["booking"])
        except ValueError:
            raise Http404 from None
        booking = get_object_or_404(Booking, pk=pk, owner=request.user)
    return render(
        request,
        "bookings/requested.html",
        {"booking": booking, "day": booking.event_date if booking else None},
    )
