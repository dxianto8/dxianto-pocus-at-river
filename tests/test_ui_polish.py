"""The UI/UX pass: one workspace navigation, event order and status, error pages, plain copy."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking

pytestmark = pytest.mark.django_db

PASSWORD = "River-Password-2026!"


def day(offset):
    return timezone.localdate() + timedelta(days=offset)


@pytest.fixture
def customer(client):
    user = get_user_model().objects.create_user("avery", "avery@example.com", PASSWORD)
    client.force_login(user)
    return user


def make(owner, offset, status="pending", session="full"):
    return Booking.objects.create(
        owner=owner,
        event_date=day(offset),
        session=session,
        status=status,
        name="Avery",
        email=owner.email,
        phone="630 555 0100",
        event_type="wedding",
        guest_count=50,
    )


class TestDashboard:
    def test_upcoming_soonest_first_then_past_most_recent_first(self, client, customer):
        far = make(customer, 90)
        old = make(customer, -60, status="confirmed")
        soon = make(customer, 10)
        recent = make(customer, -5, status="confirmed")
        response = client.get(reverse("accounts:dashboard"))
        assert list(response.context["bookings"]) == [soon, far, recent, old]

    def test_past_confirmed_events_read_as_completed(self, client, customer):
        make(customer, -5, status="confirmed")
        html = client.get(reverse("accounts:dashboard")).content.decode()
        assert "chip--completed" in html and ">Completed<" in html
        assert "This event has taken place" in html

    def test_only_filters_with_events_are_offered(self, client, customer):
        make(customer, 10)
        make(customer, 20, status="confirmed")
        values = [value for value, _ in client.get("/account/").context["filters"]]
        assert values == ["", "upcoming", "pending", "confirmed"]

    def test_there_is_one_navigation_not_a_second_tab_row(self, client, customer):
        for url in ["/account/", "/account/settings/", "/account/payments/", "/account/loyalty/"]:
            html = client.get(url).content.decode()
            assert 'aria-label="Workspace navigation"' in html
            assert "Account sections" not in html


class TestErrorPages:
    def test_missing_page_is_branded_with_a_way_back(self, client, settings):
        settings.DEBUG = False
        response = client.get("/no-such-page/")
        assert response.status_code == 404
        html = response.content.decode()
        assert "We couldn't find that page" in html
        assert 'href="/"' in html and reverse("bookings:book") in html

    def test_server_error_page_renders_without_a_request(self):
        html = render_to_string("500.html")
        assert "Something went wrong on our side" in html


class TestPlainLanguage:
    @pytest.mark.parametrize("url", ["/packages/", "/account/payments/"])
    def test_no_internal_provider_names(self, client, customer, url):
        html = client.get(url).content.decode()
        assert "Stripe" not in html and "Toast" not in html
        assert "invoice" in html

    def test_sign_in_is_called_the_same_everywhere(self, client):
        html = client.get("/explore/").content.decode()
        assert "Log in" not in html
        assert "Sign in" in html


class TestLanding:
    def test_explains_booking_and_ends_with_a_call_to_action(self, client):
        html = client.get("/explore/").content.decode()
        assert "Booking is simple." in html
        assert "morning (AM)" in html and "No account needed" in html
        assert "See it for yourself." in html
        assert html.index("See it for yourself.") > html.index("Booking is simple.")


class TestWalkthroughs:
    def test_visitors_always_get_a_way_to_arrange_a_visit(self, client):
        html = client.get("/walkthroughs/").content.decode()
        assert "No visit times are open online right now." in html
        assert "mailto:" in html and "Email the team" in html
