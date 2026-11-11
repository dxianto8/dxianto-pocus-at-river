from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import urlencode
from django.views.decorators.http import require_GET, require_http_methods

from .calendar import DayState, Month, add_months, build_month, parse_month
from .forms import BookingRequestForm, WalkthroughRequestForm
from .models import Booking, Testimonial

TAKEN_MESSAGE = "Sorry, that date was just taken by another request. Please choose another date."


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "home.html",
        {
            "testimonials": Testimonial.objects.filter(is_published=True, permission_granted=True),
        },
    )


@require_http_methods(["GET", "POST"])
def walkthrough(request: HttpRequest) -> HttpResponse:
    form = WalkthroughRequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if not form.is_spam:
            form.save()
        return redirect("walkthrough_requested")
    return render(request, "walkthrough.html", {"form": form})


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


@require_http_methods(["GET", "POST"])
def book(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()

    if request.method == "POST":
        form = BookingRequestForm(request.POST)
        if form.is_valid():
            if form.is_spam:  # pretend it worked, save nothing
                return redirect_to_requested(form.cleaned_data["event_date"])
            try:
                with transaction.atomic():
                    booking = form.save()
            except IntegrityError:  # someone else took the date between our check and the insert
                form.add_error("event_date", TAKEN_MESSAGE)
            else:
                return redirect_to_requested(booking.event_date)
        selected = safe_parse_date(request.POST.get("event_date"))
    else:
        selected = safe_parse_date(request.GET.get("date"))
        form = None

    month_param = request.GET.get("month") or (f"{selected:%Y-%m}" if selected else None)
    month = public_month(month_param, today)
    selected_state = state_of(selected, month) if selected else None
    if form is None and selected_state is DayState.AVAILABLE:
        form = BookingRequestForm(initial={"event_date": selected})

    return render(
        request,
        "bookings/book.html",
        {"month": month, "form": form, "selected": selected, "selected_state": selected_state},
    )


def redirect_to_requested(day: date) -> HttpResponse:
    return redirect(f"{reverse('bookings:requested')}?{urlencode({'date': day.isoformat()})}")


@require_GET
def requested(request: HttpRequest) -> HttpResponse:
    return render(
        request, "bookings/requested.html", {"day": safe_parse_date(request.GET.get("date"))}
    )
