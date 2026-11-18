"""AM/PM half-day bookings: a date can hold a morning and an afternoon booking separately."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from bookings.calendar import DayState
from bookings.forms import BookingEditForm, BookingRequestForm
from bookings.models import Booking

pytestmark = pytest.mark.django_db

PASSWORD = "River-Password-2026!"


def day(offset=30):
    return timezone.localdate() + timedelta(days=offset)


def make(session, status=Booking.Status.PENDING, offset=30, **fields):
    defaults = {"name": "Sam", "email": "sam@example.com", "event_type": "other", "guest_count": 40}
    return Booking.objects.create(
        event_date=day(offset), session=session, status=status, **{**defaults, **fields}
    )


def request_data(**overrides):
    return {
        "event_date": day().isoformat(),
        "session": "full",
        "name": "Avery Jones",
        "email": "avery@example.com",
        "phone": "630 555 0100",
        "event_type": "wedding",
        "guest_count": "80",
        "website": "",
        **overrides,
    }


class TestTheDatabaseKeepsHalvesApart:
    def test_am_and_pm_can_share_a_date(self):
        make("am")
        make("pm")
        assert Booking.objects.active().filter(event_date=day()).count() == 2

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("full", "am"),
            ("full", "pm"),
            ("am", "full"),
            ("pm", "full"),
            ("am", "am"),
            ("pm", "pm"),
            ("full", "full"),
        ],
    )
    def test_overlapping_halves_are_refused(self, first, second):
        make(first)
        with pytest.raises(IntegrityError), transaction.atomic():
            make(second)

    def test_a_cancelled_half_frees_it(self):
        make("am", status=Booking.Status.CANCELLED)
        make("full")  # no error

    def test_venue_blocks_a_half(self):
        make(
            "pm", status=Booking.Status.BLOCKED, name="", email="", event_type="", guest_count=None
        )
        make("am")  # no error
        with pytest.raises(IntegrityError), transaction.atomic():
            make("pm")


class TestWhatVisitorsSee:
    def test_states_for_each_half(self):
        make("am", offset=10)
        make("pm", offset=11, status=Booking.Status.CONFIRMED)
        make("am", offset=12)
        make("pm", offset=12, status=Booking.Status.CONFIRMED)
        make("am", offset=13, status=Booking.Status.CONFIRMED)
        make("pm", offset=13, status=Booking.Status.BLOCKED)
        states = Booking.objects.public_states(day(0), day(20))
        assert states[day(10)] == DayState.PM_OPEN
        assert states[day(11)] == DayState.AM_OPEN
        assert states[day(12)] == DayState.ON_HOLD  # one half is still only requested
        assert states[day(13)] == DayState.BOOKED
        assert day(14) not in states

    def test_open_sessions(self):
        assert Booking.objects.open_sessions(day()) == ["full", "am", "pm"]
        booking = make("am")
        assert Booking.objects.open_sessions(day()) == ["pm"]
        assert Booking.objects.open_sessions(day(), exclude_pk=booking.pk) == ["full", "am", "pm"]
        make("pm")
        assert Booking.objects.open_sessions(day()) == []

    def test_calendar_labels_the_open_half_and_links_to_it(self, client):
        make("pm")
        response = client.get("/book/", {"month": f"{day():%Y-%m}"})
        html = response.content.decode()
        assert "AM open" in html
        assert f"date={day():%Y-%m-%d}" in html

    def test_request_form_offers_only_the_open_half(self, client):
        make("am")
        response = client.get("/book/", {"date": day().isoformat()})
        form = response.context["form"]
        assert [value for value, _ in form.fields["session"].choices] == ["pm"]
        assert form.initial["session"] == "pm"
        assert "The morning is taken" in response.content.decode()


class TestRequestingHalfADay:
    def test_book_the_afternoon_when_the_morning_is_taken(self, client):
        make("am")
        response = client.post("/book/", request_data(session="pm"))
        assert response.status_code == 302
        booking = Booking.objects.get(session="pm")
        assert booking.status == Booking.Status.PENDING

    @pytest.mark.parametrize("session", ["full", "am"])
    def test_taken_half_is_refused(self, session):
        make("am")
        form = BookingRequestForm(request_data(session=session))
        assert not form.is_valid()
        assert "session" in form.errors

    def test_date_with_both_halves_taken_is_refused(self):
        make("am")
        make("pm")
        form = BookingRequestForm(request_data(session="pm"))
        assert not form.is_valid()
        assert "event_date" in form.errors

    def test_missing_choice_means_the_full_day(self):
        data = request_data()
        del data["session"]
        form = BookingRequestForm(data)
        assert form.is_valid(), form.errors
        assert form.save().session == "full"

    @pytest.mark.parametrize(
        ("session", "start", "end", "ok"),
        [
            ("am", "09:00", "11:30", True),
            ("am", "13:00", "15:00", False),
            ("pm", "11:00", "15:00", False),
            ("pm", "17:00", "23:00", True),
            ("full", "09:00", "23:00", True),
        ],
    )
    def test_times_must_fit_the_half(self, session, start, end, ok):
        form = BookingRequestForm(request_data(session=session, start_time=start, end_time=end))
        assert form.is_valid() is ok
        if not ok:
            assert "start_time" in form.errors

    def test_half_appears_in_the_confirmation_and_venue_email(self, client, mailoutbox):
        client.post("/book/", request_data(session="pm"))
        booking = Booking.objects.get()
        page = client.get(reverse("bookings:requested"), {"booking": booking.pk})
        assert "· PM" in page.content.decode()
        venue_mail = next(m for m in mailoutbox if "New request" in m.subject)
        assert "(PM)" in venue_mail.subject


class TestChangingTheHalf:
    @pytest.fixture
    def owner(self):
        return get_user_model().objects.create_user("owner", "owner@example.com", PASSWORD)

    def edit_data(self, booking, **overrides):
        return {
            "event_date": booking.event_date.isoformat(),
            "session": booking.session,
            "name": booking.name,
            "phone": "630 555 0100",
            "event_type": booking.event_type,
            "guest_count": booking.guest_count,
            **overrides,
        }

    def test_move_from_morning_to_afternoon(self, client, owner):
        booking = make("am", owner=owner, event_type="wedding")
        client.force_login(owner)
        response = client.post(
            reverse("accounts:booking_edit", args=[booking.pk]),
            self.edit_data(booking, session="pm"),
        )
        assert response.status_code == 302
        booking.refresh_from_db()
        assert booking.session == "pm"
        assert booking.activity.filter(text__contains="to ").filter(text__contains="PM").exists()

    def test_cannot_move_onto_a_taken_half(self, owner):
        booking = make("am", owner=owner, event_type="wedding")
        make("pm")
        form = BookingEditForm(self.edit_data(booking, session="full"), instance=booking)
        assert not form.is_valid()
        assert "session" in form.errors

    def test_keeping_the_same_half_is_always_allowed(self, owner):
        booking = make("pm", owner=owner, event_type="wedding")
        make("am")
        form = BookingEditForm(self.edit_data(booking, guest_count=55), instance=booking)
        assert form.is_valid(), form.errors


class TestAdminCalendar:
    def test_block_one_half_and_see_both(self, admin_client):
        make("am", offset=12)
        response = admin_client.post(
            reverse("admin:bookings_booking_block"),
            {"date": day(12).isoformat(), "session": "pm"},
        )
        assert response.status_code == 302
        assert Booking.objects.get(session="pm").status == Booking.Status.BLOCKED
        page = admin_client.get(
            reverse("admin:bookings_booking_calendar"), {"month": f"{day(12):%Y-%m}"}
        )
        cell = next(d for week in page.context["weeks"] for d in week if d.date == day(12))
        assert [b.session for b in cell.bookings] == ["am", "pm"]
        assert cell.open_sessions == []

    def test_blocking_a_taken_half_is_refused(self, admin_client):
        make("am", offset=12)
        admin_client.post(
            reverse("admin:bookings_booking_block"),
            {"date": day(12).isoformat(), "session": "full"},
        )
        assert Booking.objects.count() == 1
