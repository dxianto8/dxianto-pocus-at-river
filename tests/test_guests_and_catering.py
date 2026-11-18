"""Booking without an account, and ordering catering from the menu."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, CateringItem, CateringOrder

pytestmark = pytest.mark.django_db

PASSWORD = "River-Password-2026!"


def day(offset=30):
    return timezone.localdate() + timedelta(days=offset)


def request_data(**overrides):
    return {
        "event_date": day().isoformat(),
        "session": "full",
        "name": "Avery Jones",
        "email": "avery@example.com",
        "phone": "630 555 0100",
        "event_type": "wedding",
        "guest_count": "80",
        "catering_interest": "False",
        "website": "",
        **overrides,
    }


@pytest.fixture
def menu():
    return [
        CateringItem.objects.create(
            title="Grazing board",
            category="Starters",
            description="Cheese and fruit",
            price=Decimal("12.50"),
            price_note="per person",
            is_published=True,
        ),
        CateringItem.objects.create(
            title="Signature cake",
            category="Desserts",
            description="Three tiers",
            price=None,
            is_published=True,
        ),
        CateringItem.objects.create(
            title="Hidden item", category="Desserts", description="Draft", is_published=False
        ),
    ]


def guest_booking(client, **overrides):
    response = client.post("/book/", request_data(**overrides))
    return Booking.objects.get(), response


class TestGuestRequests:
    def test_guest_can_see_their_own_confirmation_but_others_cannot(self, client):
        booking, response = guest_booking(client)
        assert booking.owner is None
        page = client.get(response.url)
        assert page.status_code == 200
        assert b"Create an account" in page.content
        assert b'class="site-header"' in page.content  # public layout, not the workspace
        assert Client().get(response.url).status_code == 404

    def test_guest_gets_an_email_and_the_venue_hears_about_it(self, client, mailoutbox):
        guest_booking(client)
        to_guest = [m for m in mailoutbox if m.to == ["avery@example.com"]]
        assert to_guest and "We received your request" in to_guest[0].subject
        assert "630 555 0100" in next(m for m in mailoutbox if "New request" in m.subject).body

    def test_status_emails_reach_guests_at_the_request_email(self, admin_client, mailoutbox):
        booking = Booking.objects.create(
            event_date=day(),
            name="Avery",
            email="avery@example.com",
            phone="630 555 0100",
            event_type="wedding",
            guest_count=80,
        )
        admin_client.post(
            reverse("admin:bookings_booking_changelist"),
            {"action": "confirm", "_selected_action": [booking.pk]},
        )
        assert any(m.to == ["avery@example.com"] and "confirmed" in m.subject for m in mailoutbox)

    def test_signing_up_in_the_same_browser_claims_the_request(self, client):
        booking, _ = guest_booking(client)
        client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Avery",
                "email": "avery@example.com",
                "username": "avery",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        booking.refresh_from_db()
        assert booking.owner.username == "avery"
        assert client.get(reverse("accounts:booking_detail", args=[booking.pk])).status_code == 200

    def test_signing_in_claims_it_too_but_another_browser_cannot(self, client):
        user = get_user_model().objects.create_user("avery", "avery@example.com", PASSWORD)
        booking, _ = guest_booking(client)
        other = Client()
        other.post(reverse("accounts:login"), {"username": "avery", "password": PASSWORD})
        booking.refresh_from_db()
        assert booking.owner is None  # same email, different browser: never matched
        client.post(reverse("accounts:login"), {"username": "avery", "password": PASSWORD})
        booking.refresh_from_db()
        assert booking.owner == user

    def test_signed_in_booking_saves_the_phone_to_the_profile(self, client):
        user = get_user_model().objects.create_user("avery", "avery@example.com", PASSWORD)
        client.force_login(user)
        client.post("/book/", request_data())
        assert user.profile.phone == "630 555 0100"
        form = client.get("/book/", {"date": day(40).isoformat()}).context["form"]
        assert form.initial["phone"] == "630 555 0100"


class TestCateringQuestion:
    def test_yes_leads_straight_to_the_order_page_for_that_request(self, client, menu):
        booking, response = guest_booking(client, catering_interest="True")
        assert booking.catering_interest
        assert response.url == f"{reverse('catering_order')}?booking={booking.pk}"
        page = client.get(response.url)
        assert page.status_code == 200
        html = page.content.decode()
        assert "Grazing board" in html and "Hidden item" not in html
        assert booking.when in html

    def test_no_goes_to_the_confirmation(self, client):
        _, response = guest_booking(client)
        assert response.url.startswith(reverse("bookings:requested"))

    def test_question_is_on_the_request_form(self, client):
        response = client.get("/book/", {"date": day().isoformat()})
        assert "Do you want to order catering with us?" in response.content.decode()


class TestOrderingCatering:
    def order(self, client, booking, menu, **overrides):
        data = {
            "name": "Avery Jones",
            "email": "avery@example.com",
            "phone": "630 555 0100",
            "guest_count": "80",
            f"qty_{menu[0].pk}": "80",
            f"qty_{menu[1].pk}": "1",
            "notes": "Two vegan guests",
            "website": "",
            **overrides,
        }
        return client.post(f"{reverse('catering_order')}?booking={booking.pk}", data)

    def test_order_copies_prices_and_totals_the_priced_items(self, client, menu, mailoutbox):
        booking, _ = guest_booking(client, catering_interest="True")
        response = self.order(client, booking, menu)
        order = CateringOrder.objects.get()
        assert response.url == reverse("catering_order_detail", args=[order.pk])
        assert order.booking == booking
        assert order.event_date == booking.event_date
        assert order.total == Decimal("1000.00")
        assert order.has_unpriced_items
        assert order.total_display == "$1,000.00 + quoted items"
        assert {(line.title, line.quantity) for line in order.lines.all()} == {
            ("Grazing board", 80),
            ("Signature cake", 1),
        }
        menu[0].price = Decimal("99")
        menu[0].save()
        order.refresh_from_db()
        assert order.total == Decimal("1000.00")
        assert order.lines.get(title="Grazing board").unit_price == Decimal("12.50")
        receipt = client.get(response.url)
        assert receipt.status_code == 200
        assert b"$1,000.00" in receipt.content
        assert Client().get(response.url).status_code == 404
        subjects = [m.subject for m in mailoutbox]
        assert any("New catering order" in s for s in subjects)
        assert any("Your catering order" in s for s in subjects)
        assert booking.activity.filter(text__startswith="You ordered catering").exists()

    def test_at_least_one_item_is_needed(self, client, menu):
        booking, _ = guest_booking(client)
        response = self.order(
            client, booking, menu, **{f"qty_{menu[0].pk}": "", f"qty_{menu[1].pk}": "0"}
        )
        assert response.status_code == 200
        assert not CateringOrder.objects.exists()
        assert "Choose at least one item" in response.content.decode()

    @pytest.mark.parametrize("quantity", ["-1", "1001", "lots"])
    def test_bad_quantities_are_refused(self, client, menu, quantity):
        booking, _ = guest_booking(client)
        self.order(client, booking, menu, **{f"qty_{menu[0].pk}": quantity})
        assert not CateringOrder.objects.exists()

    def test_unpublished_items_cannot_be_ordered(self, client, menu):
        booking, _ = guest_booking(client)
        self.order(client, booking, menu, **{f"qty_{menu[2].pk}": "5"})
        assert not CateringOrder.objects.get().lines.filter(title="Hidden item").exists()

    def test_someone_elses_request_cannot_be_used(self, client, menu):
        booking, _ = guest_booking(client)
        stranger = Client()
        assert stranger.get(f"{reverse('catering_order')}?booking={booking.pk}").status_code == 404
        assert self.order(stranger, booking, menu).status_code == 404
        assert not CateringOrder.objects.exists()

    def test_order_without_a_booking_needs_a_date(self, client, menu):
        data = {
            "name": "Avery",
            "email": "avery@example.com",
            "phone": "630 555 0100",
            f"qty_{menu[0].pk}": "10",
        }
        response = client.post(reverse("catering_order"), data)
        assert "event_date" in response.context["form"].errors
        response = client.post(reverse("catering_order"), {**data, "event_date": day(5)})
        order = CateringOrder.objects.get()
        assert order.booking is None and order.event_date == day(5)
        assert client.get(response.url).status_code == 200

    def test_signed_in_customer_picks_one_of_their_events(self, client, menu):
        user = get_user_model().objects.create_user("avery", "avery@example.com", PASSWORD)
        client.force_login(user)
        client.post("/book/", request_data())
        booking = Booking.objects.get()
        client.post(
            reverse("catering_order"),
            {
                "event": booking.pk,
                "name": "Avery",
                "email": "avery@example.com",
                "phone": "630 555 0100",
                f"qty_{menu[0].pk}": "2",
            },
        )
        order = CateringOrder.objects.get()
        assert order.booking == booking and order.owner == user
        detail = client.get(reverse("accounts:booking_detail", args=[booking.pk]))
        assert order.total_display.encode() in detail.content

    def test_guest_orders_are_claimed_on_sign_up(self, client, menu):
        booking, _ = guest_booking(client)
        self.order(client, booking, menu)
        client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Avery",
                "email": "avery@example.com",
                "username": "avery",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        assert CateringOrder.objects.get().owner.username == "avery"

    def test_empty_menu_takes_a_written_request(self, client):
        booking, _ = guest_booking(client)
        url = f"{reverse('catering_order')}?booking={booking.pk}"
        contact = {"name": "Avery", "email": "avery@example.com", "phone": "630 555 0100"}
        response = client.post(url, contact)
        assert "notes" in response.context["form"].errors
        client.post(url, {**contact, "notes": "Tacos for 80, please"})
        order = CateringOrder.objects.get()
        assert order.notes == "Tacos for 80, please" and order.total == 0

    def test_honeypot_saves_nothing(self, client, menu):
        booking, _ = guest_booking(client)
        response = self.order(client, booking, menu, website="http://spam.example")
        assert response.status_code == 302
        assert not CateringOrder.objects.exists()

    def test_menu_page_links_to_ordering(self, client, menu):
        html = client.get(reverse("catering")).content.decode()
        assert reverse("catering_order") in html
        assert "Do you want to order catering with us?" in html


class TestSigningUpAfterARequest:
    """A visitor who just requested a date should not be asked for their name and email again."""

    signup = {
        "username": "averyj",
        "password1": PASSWORD,
        "password2": PASSWORD,
        "next": "/account/",
    }

    def test_signup_form_starts_with_the_requests_name_and_email(self, client):
        guest_booking(client)
        form = client.get(reverse("accounts:signup")).context["form"]
        assert form["first_name"].value() == "Avery Jones"
        assert form["email"].value() == "avery@example.com"

    def test_only_username_and_password_are_needed_and_everything_carries_over(self, client):
        booking, _ = guest_booking(client)
        response = client.post(
            reverse("accounts:signup"),
            {**self.signup, "first_name": "Avery Jones", "email": "avery@example.com"},
        )
        assert response.status_code == 302
        user = get_user_model().objects.get(username="averyj")
        booking.refresh_from_db()
        assert booking.owner == user
        assert user.email == "avery@example.com"
        assert user.profile.phone == "630 555 0100"

    def test_another_browser_gets_a_blank_form(self, client):
        guest_booking(client)
        form = Client().get(reverse("accounts:signup")).context["form"]
        assert form["first_name"].value() is None and form["email"].value() is None

    def test_signup_without_a_request_says_an_account_is_optional(self, client):
        page = client.get(reverse("accounts:signup")).content.decode()
        assert "free and optional" in page
        assert "You need an account to request a date" not in page


def test_account_without_an_email_can_still_request_and_keeps_the_email(client):
    user = get_user_model().objects.create_user("noemail", "", PASSWORD)
    client.force_login(user)
    form = client.get("/book/", {"date": day().isoformat()}).context["form"]
    assert not form.fields["email"].disabled  # never a locked, empty required field
    response = client.post("/book/", request_data(email="found@example.com"))
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.email == "found@example.com"
    assert Booking.objects.get().email == "found@example.com"


def test_account_with_an_email_cannot_change_it_from_the_request_form(client):
    user = get_user_model().objects.create_user("hasemail", "kept@example.com", PASSWORD)
    client.force_login(user)
    client.post("/book/", request_data(email="other@example.com"))
    assert Booking.objects.get().email == "kept@example.com"
