from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from bookings.forms import BookingRequestForm
from bookings.models import Booking

pytestmark = pytest.mark.django_db

BOOK = "/book/"


@pytest.fixture(autouse=True)
def signed_in(client):
    user = get_user_model().objects.create_user(
        "guest", "avery@example.com", "River-Password-2026!"
    )
    client.force_login(user)
    return user


def day(offset: int):
    return timezone.localdate() + timedelta(days=offset)


def post_data(event_date, **overrides):
    data = {
        "event_date": event_date.isoformat(),
        "name": "Avery Jones",
        "email": "avery@example.com",
        "event_type": "wedding",
        "guest_count": "120",
        "website": "",
    }
    return {**data, **overrides}


def test_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"A place with a story." in response.content
    assert b'href="/book/"' in response.content


class TestBookPage:
    def test_shows_this_month_with_states_but_no_personal_details(self, client):
        Booking.objects.create(
            event_date=day(3),
            status=Booking.Status.CONFIRMED,
            name="Secret Name",
            email="secret@example.com",
            event_type="wedding",
            guest_count=80,
        )
        response = client.get(BOOK, {"month": f"{day(3):%Y-%m}"})
        assert response.status_code == 200
        html = response.content.decode()
        assert day(3).strftime("%B %Y") in html
        assert "Booked" in html
        assert "Secret Name" not in html
        assert "secret@example.com" not in html

    def test_picking_an_available_date_shows_the_form(self, client):
        response = client.get(BOOK, {"date": day(10).isoformat()})
        assert isinstance(response.context["form"], BookingRequestForm)
        assert response.context["form"].initial["event_date"] == day(10)

    def test_picking_a_taken_date_shows_no_form(self, client):
        Booking.objects.create(event_date=day(10), status=Booking.Status.BLOCKED)
        response = client.get(BOOK, {"date": day(10).isoformat()})
        assert response.context["form"] is None
        assert "isn't available" in response.content.decode()

    def test_nonsense_dates_are_ignored(self, client):
        response = client.get(BOOK, {"date": "2026-02-30", "month": "banana"})
        assert response.status_code == 200
        assert response.context["form"] is None


class TestSubmittingARequest:
    def test_creates_a_pending_booking_and_redirects(self, client):
        response = client.post(BOOK, post_data(day(20)))
        booking = Booking.objects.get()
        assert booking.status == Booking.Status.PENDING
        assert booking.event_date == day(20)
        assert response.status_code == 302
        assert response["Location"] == f"{reverse('bookings:requested')}?booking={booking.pk}"

    def test_thank_you_page_names_the_date(self, client):
        client.post(BOOK, post_data(day(20)))
        response = client.get(reverse("bookings:requested"), {"booking": Booking.objects.get().pk})
        assert day(20).strftime("%B") in response.content.decode()

    def test_date_shows_on_hold_afterwards(self, client):
        client.post(BOOK, post_data(day(20)))
        response = client.get(BOOK, {"month": f"{day(20):%Y-%m}"})
        assert "On hold" in response.content.decode()

    def test_honeypot_saves_nothing_but_looks_successful(self, client):
        response = client.post(BOOK, post_data(day(20), website="http://spam.example"))
        assert response.status_code == 302
        assert not Booking.objects.exists()

    def test_taken_date_is_refused_with_a_message(self, client):
        client.post(BOOK, post_data(day(20)))
        response = client.post(BOOK, post_data(day(20), email="other@example.com"))
        assert response.status_code == 200
        assert Booking.objects.count() == 1
        assert "no longer available" in response.content.decode()

    def test_race_between_check_and_insert_is_handled(self, client, monkeypatch):
        """If another request wins between validation and saving, the database refuses the
        second insert and the visitor gets a friendly message instead of an error page."""

        def lose_the_race(self, commit=True):
            raise IntegrityError("duplicate key value violates unique constraint")

        monkeypatch.setattr(BookingRequestForm, "save", lose_the_race)
        response = client.post(BOOK, post_data(day(20)))
        assert response.status_code == 200
        assert "just taken" in response.content.decode()
