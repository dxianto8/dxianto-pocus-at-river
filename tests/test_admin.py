from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:bookings_booking_changelist")
CALENDAR = reverse("admin:bookings_booking_calendar")
BLOCK = reverse("admin:bookings_booking_block")


def day(offset: int):
    return timezone.localdate() + timedelta(days=offset)


def booking(offset: int, status=Booking.Status.PENDING, name="Avery Jones"):
    return Booking.objects.create(
        event_date=day(offset),
        status=status,
        name=name,
        email="avery@example.com",
        event_type="wedding",
        guest_count=100,
    )


def run_action(client, action, *bookings):
    return client.post(
        CHANGELIST,
        {"action": action, "_selected_action": [str(b.pk) for b in bookings]},
        follow=True,
    )


class TestAccess:
    @pytest.mark.parametrize("url", [CHANGELIST, CALENDAR])
    def test_requires_login(self, client, url):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("admin:login") in response["Location"]

    def test_block_requires_login(self, client):
        response = client.post(BLOCK, {"date": day(5).isoformat()})
        assert response.status_code == 302
        assert not Booking.objects.exists()


class TestList:
    def test_pending_requests_come_first(self, admin_client):
        booking(1, Booking.Status.CONFIRMED, name="Early Confirmed")
        booking(30, Booking.Status.PENDING, name="Later Pending")
        response = admin_client.get(CHANGELIST)
        names = [b.name for b in response.context["cl"].result_list]
        assert names == ["Later Pending", "Early Confirmed"]


class TestActions:
    def test_confirm_moves_pending_to_confirmed(self, admin_client):
        b = booking(10)
        run_action(admin_client, "confirm", b)
        b.refresh_from_db()
        assert b.status == Booking.Status.CONFIRMED

    def test_decline_frees_the_date(self, admin_client):
        b = booking(10)
        run_action(admin_client, "decline", b)
        b.refresh_from_db()
        assert b.status == Booking.Status.DECLINED
        booking(10, name="Next In Line")  # the date can be requested again

    def test_cancel_frees_a_confirmed_date(self, admin_client):
        b = booking(10, Booking.Status.CONFIRMED)
        run_action(admin_client, "cancel", b)
        b.refresh_from_db()
        assert b.status == Booking.Status.CANCELLED

    def test_confirm_skips_bookings_that_are_not_pending(self, admin_client):
        b = booking(10, Booking.Status.CANCELLED)
        response = run_action(admin_client, "confirm", b)
        b.refresh_from_db()
        assert b.status == Booking.Status.CANCELLED
        assert "Skipped 1" in response.content.decode()


class TestEditing:
    def test_changing_a_booking_to_a_taken_date_is_refused(self, admin_client):
        booking(10, Booking.Status.CONFIRMED)
        other = booking(11)
        url = reverse("admin:bookings_booking_change", args=[other.pk])
        response = admin_client.post(
            url,
            {
                "event_date": day(10).isoformat(),
                "status": "pending",
                "name": other.name,
                "email": other.email,
                "phone": "",
                "event_type": "wedding",
                "guest_count": "100",
                "message": "",
                "admin_note": "",
            },
        )
        assert response.status_code == 200  # form shown again with an error
        other.refresh_from_db()
        assert other.event_date == day(11)

    def test_add_form_can_be_prefilled_with_a_date(self, admin_client):
        response = admin_client.get(
            reverse("admin:bookings_booking_add"), {"event_date": day(12).isoformat()}
        )
        assert response.context["adminform"].form.initial["event_date"] == day(12).isoformat()


class TestCalendar:
    def test_shows_bookings_with_names_for_staff(self, admin_client):
        booking(3, Booking.Status.CONFIRMED, name="Morgan & Riley")
        response = admin_client.get(CALENDAR, {"month": f"{day(3):%Y-%m}"})
        assert response.status_code == 200
        assert "Morgan &amp; Riley" in response.content.decode()

    def test_block_and_unblock_a_date(self, admin_client):
        admin_client.post(BLOCK, {"date": day(5).isoformat()})
        blocked = Booking.objects.get()
        assert blocked.status == Booking.Status.BLOCKED
        assert blocked.event_date == day(5)

        admin_client.post(reverse("admin:bookings_booking_unblock", args=[blocked.pk]))
        assert not Booking.objects.exists()

    def test_blocking_a_taken_date_shows_an_error(self, admin_client):
        booking(5)
        response = admin_client.post(BLOCK, {"date": day(5).isoformat()}, follow=True)
        assert Booking.objects.count() == 1
        assert "already has a booking" in response.content.decode()

    def test_cannot_block_a_past_date(self, admin_client):
        admin_client.post(BLOCK, {"date": day(-1).isoformat()})
        assert not Booking.objects.exists()

    def test_unblock_only_removes_blocks(self, admin_client):
        b = booking(5, Booking.Status.CONFIRMED)
        response = admin_client.post(reverse("admin:bookings_booking_unblock", args=[b.pk]))
        assert response.status_code == 404
        assert Booking.objects.filter(pk=b.pk).exists()
