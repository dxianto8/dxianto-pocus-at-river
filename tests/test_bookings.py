from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from bookings.calendar import DayState, add_months
from bookings.forms import BookingRequestForm
from bookings.models import Booking

pytestmark = pytest.mark.django_db


def today():
    return timezone.localdate()


def request_data(**overrides):
    data = {
        "event_date": (today() + timedelta(days=30)).isoformat(),
        "name": "Avery Jones",
        "email": "avery@example.com",
        "phone": "",
        "event_type": "wedding",
        "guest_count": "120",
        "message": "Saturday evening reception",
        "website": "",
    }
    data.update(overrides)
    return data


def make_booking(days_ahead=30, status=Booking.Status.PENDING, **fields):
    defaults = {
        "name": "Sam Lee",
        "email": "sam@example.com",
        "event_type": "corporate",
        "guest_count": 40,
    }
    if status == Booking.Status.BLOCKED:
        defaults = {}
    return Booking.objects.create(
        event_date=today() + timedelta(days=days_ahead), status=status, **{**defaults, **fields}
    )


class TestOneActiveBookingPerDate:
    @pytest.mark.parametrize(
        "status", [Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.BLOCKED]
    )
    def test_active_bookings_block_the_date(self, status):
        make_booking(status=status)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_booking(status=Booking.Status.PENDING)

    @pytest.mark.parametrize("status", [Booking.Status.DECLINED, Booking.Status.CANCELLED])
    def test_declined_and_cancelled_bookings_free_the_date(self, status):
        make_booking(status=status)
        make_booking(status=Booking.Status.PENDING)  # no error
        assert Booking.objects.count() == 2


class TestPublicStates:
    def test_maps_statuses_to_what_visitors_see(self):
        pending = make_booking(10, Booking.Status.PENDING)
        confirmed = make_booking(11, Booking.Status.CONFIRMED)
        blocked = make_booking(12, Booking.Status.BLOCKED)
        make_booking(13, Booking.Status.DECLINED)

        states = Booking.objects.public_states(today(), today() + timedelta(days=20))
        assert states == {
            pending.event_date: DayState.ON_HOLD,
            confirmed.event_date: DayState.BOOKED,
            blocked.event_date: DayState.BOOKED,
        }


class TestBookingRequestForm:
    def test_valid_request(self):
        form = BookingRequestForm(request_data())
        assert form.is_valid(), form.errors
        booking = form.save()
        assert booking.status == Booking.Status.PENDING
        assert not form.is_spam

    @pytest.mark.parametrize("field", ["name", "email", "event_type", "guest_count", "event_date"])
    def test_required_fields(self, field):
        form = BookingRequestForm(request_data(**{field: ""}))
        assert not form.is_valid()
        assert field in form.errors

    def test_rejects_past_dates(self):
        form = BookingRequestForm(
            request_data(event_date=(today() - timedelta(days=1)).isoformat())
        )
        assert not form.is_valid()
        assert "event_date" in form.errors

    def test_rejects_dates_more_than_24_months_ahead(self):
        too_far = add_months(today(), 24) + timedelta(days=1)
        form = BookingRequestForm(request_data(event_date=too_far.isoformat()))
        assert not form.is_valid()
        assert "event_date" in form.errors

    def test_rejects_dates_already_taken(self):
        taken = make_booking(30, Booking.Status.CONFIRMED)
        form = BookingRequestForm(request_data(event_date=taken.event_date.isoformat()))
        assert not form.is_valid()
        assert form.errors["event_date"] == ["Sorry, that date is no longer available."]

    @pytest.mark.parametrize("guests", ["0", "201"])
    def test_guest_count_limits(self, guests):
        form = BookingRequestForm(request_data(guest_count=guests))
        assert not form.is_valid()
        assert "guest_count" in form.errors

    def test_honeypot_marks_submission_as_spam(self):
        form = BookingRequestForm(request_data(website="http://spam.example"))
        assert form.is_valid()
        assert form.is_spam

    def test_ignores_status_sent_by_the_visitor(self):
        form = BookingRequestForm(request_data(status="confirmed"))
        assert form.is_valid()
        assert form.save().status == Booking.Status.PENDING


class TestModelValidation:
    def test_requests_need_contact_details_but_blocks_do_not(self):
        blocked = Booking(event_date=today() + timedelta(days=5), status=Booking.Status.BLOCKED)
        blocked.full_clean()  # no error

        bare = Booking(event_date=today() + timedelta(days=6), status=Booking.Status.CONFIRMED)
        with pytest.raises(ValidationError) as exc:
            bare.full_clean()
        assert {"name", "email"} <= set(exc.value.message_dict)
