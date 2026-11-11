import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, EventPackage, VenueSettings

pytestmark = pytest.mark.django_db
PASSWORD = "River-Planning-2026!"


@pytest.fixture
def customer():
    return get_user_model().objects.create_user(
        username="riverguest", email="guest@example.com", password=PASSWORD, first_name="Avery"
    )


def signup_data(**overrides):
    return {
        "first_name": "Avery",
        "email": "avery@example.com",
        "username": "avery",
        "password1": PASSWORD,
        "password2": PASSWORD,
        **overrides,
    }


def booking_data(**overrides):
    return {
        "event_date": (timezone.localdate() + timedelta(days=20)).isoformat(),
        "name": "Avery",
        "email": "attacker@example.com",
        "event_type": "wedding",
        "guest_count": "80",
        "message": "Ceremony and reception.",
        **overrides,
    }


def make_booking(owner, **overrides):
    return Booking.objects.create(
        owner=owner,
        **{**booking_data(), "email": owner.email if owner else "guest@example.com", **overrides},
    )


def test_signup_hashes_password_starts_session_and_keeps_event_destination(client):
    response = client.post(reverse("accounts:signup"), signup_data(next="/book/?date=2027-01-20"))
    user = get_user_model().objects.get(username="avery")
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD
    assert not user.is_staff and not user.is_superuser
    assert client.session["_auth_user_id"] == str(user.pk)
    assert response.url == "/book/?date=2027-01-20"


@pytest.mark.parametrize(
    "next_url", ["https://evil.example/", "//evil.example/", "javascript:alert(1)"]
)
def test_signup_rejects_external_redirects(client, next_url):
    response = client.post(reverse("accounts:signup"), signup_data(next=next_url))
    assert response.url == reverse("accounts:dashboard")


def test_signup_rejects_weak_password_and_duplicate_username(client, customer):
    response = client.post(
        reverse("accounts:signup"), signup_data(password1="123", password2="123")
    )
    assert "password2" in response.context["form"].errors
    response = client.post(reverse("accounts:signup"), signup_data(username=customer.username))
    assert "username" in response.context["form"].errors
    assert get_user_model().objects.count() == 1


def test_login_and_post_only_logout(client, customer):
    response = client.post(
        reverse("accounts:login"), {"username": customer.username, "password": PASSWORD}
    )
    assert response.url == reverse("accounts:dashboard")
    assert client.get(reverse("accounts:logout")).status_code == 405
    assert client.post(reverse("accounts:logout")).url == "/"
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("method", ["get", "post"])
def test_anonymous_visitors_cannot_book_even_with_forged_owner(client, customer, method):
    response = getattr(client, method)(
        "/book/", booking_data(owner=customer.pk, status="confirmed")
    )
    assert response.status_code == 302
    assert response.url.startswith("/account/login/?next=")
    assert not Booking.objects.exists()


def test_owner_status_email_and_package_snapshot_are_server_controlled(client, customer):
    client.force_login(customer)
    package = EventPackage.objects.get(slug="wedding")
    package.price = Decimal("2500")
    package.inclusions = "Venue rental\nTables and chairs"
    package.save()
    response = client.post(
        "/book/", booking_data(owner=9999, status="confirmed", package=package.pk)
    )
    booking = Booking.objects.get()
    assert booking.owner == customer
    assert booking.email == customer.email
    assert booking.status == Booking.Status.PENDING
    assert booking.package_snapshot == package.title
    assert booking.price_snapshot == "From $2,500 per event"
    assert response.url.endswith(f"?booking={booking.pk}")
    package.price = Decimal("3500")
    package.title = "New name"
    package.save()
    booking.refresh_from_db()
    assert booking.price_snapshot == "From $2,500 per event"
    assert booking.package_snapshot != package.title


def test_customer_cannot_select_unpublished_or_mismatched_packages(client, customer):
    client.force_login(customer)
    package = EventPackage.objects.get(slug="wedding")
    package.is_published = False
    package.save()
    response = client.post("/book/", booking_data(package=package.pk))
    assert "package" in response.context["form"].errors
    package.is_published = True
    package.save()
    response = client.post("/book/", booking_data(package=package.pk, event_type="corporate"))
    assert "package" in response.context["form"].errors
    assert not Booking.objects.exists()


def test_dashboard_and_detail_do_not_expose_other_or_legacy_bookings(client, customer):
    other = get_user_model().objects.create_user("other", "other@example.com", PASSWORD)
    owned = make_booking(customer, message="My own notes", admin_note="STAFF ONLY")
    hidden = make_booking(
        other, event_date=timezone.localdate() + timedelta(days=21), name="Private Guest"
    )
    legacy = make_booking(
        None, event_date=timezone.localdate() + timedelta(days=22), name="Legacy Guest"
    )
    client.force_login(customer)
    response = client.get(reverse("accounts:dashboard"))
    assert "no-store" in response["Cache-Control"]
    html = response.content.decode()
    assert str(owned.pk) in html
    assert "Private Guest" not in html and "Legacy Guest" not in html
    assert str(hidden.pk) not in html and str(legacy.pk) not in html
    assert (
        "STAFF ONLY"
        not in client.get(reverse("accounts:booking_detail", args=[owned.pk])).content.decode()
    )
    for booking in [hidden, legacy]:
        assert client.get(reverse("accounts:booking_detail", args=[booking.pk])).status_code == 404
        assert client.get("/book/requested/", {"booking": booking.pk}).status_code == 404
    assert client.get("/book/requested/", {"booking": "invalid"}).status_code == 404


@pytest.mark.parametrize("status", ["pending", "confirmed", "declined", "cancelled"])
def test_dashboard_reflects_staff_status_changes(client, customer, status):
    booking = make_booking(customer, status=status)
    client.force_login(customer)
    html = client.get(reverse("accounts:dashboard")).content.decode()
    assert booking.get_status_display() in html
    assert booking.status_description in html


def test_password_reset_delivers_safe_link_and_token_is_single_use(client, customer, mailoutbox):
    response = client.post(reverse("accounts:password_reset"), {"email": customer.email})
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mailoutbox) == 1
    link = re.search(r"http://testserver(/account/reset/[^\s]+)", mailoutbox[0].body).group(1)
    response = client.get(link)
    assert response.status_code == 302
    reset_url = response.url
    new_password = "New-River-Password-2027!"
    response = client.post(
        reset_url, {"new_password1": new_password, "new_password2": new_password}
    )
    assert response.url == reverse("accounts:password_reset_complete")
    customer.refresh_from_db()
    assert customer.check_password(new_password)
    assert client.get(link).context["validlink"] is False


def test_unknown_password_reset_email_has_same_response_without_mail(client, mailoutbox):
    response = client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
    assert response.url == reverse("accounts:password_reset_done")
    assert not mailoutbox


def test_sensitive_forms_require_csrf(customer):
    client = Client(enforce_csrf_checks=True)
    assert client.post(reverse("accounts:signup"), signup_data()).status_code == 403
    assert (
        client.post(
            reverse("accounts:login"), {"username": customer.username, "password": PASSWORD}
        ).status_code
        == 403
    )
    client.force_login(customer)
    assert client.post("/book/", booking_data()).status_code == 403
    assert client.post(reverse("accounts:logout")).status_code == 403


def test_admin_settings_and_packages_update_public_page(admin_client, client):
    package = EventPackage.objects.get(slug="wedding")
    response = admin_client.post(
        reverse("admin:bookings_eventpackage_change", args=[package.pk]),
        {
            "title": "Evening wedding",
            "slug": package.slug,
            "event_type": "wedding",
            "description": "An evening celebration.",
            "price": "4200",
            "price_unit": "event",
            "starting_at": "on",
            "inclusions": "Confirmed rental inclusion\nAnother inclusion",
            "is_published": "on",
            "display_order": 0,
        },
    )
    assert response.status_code == 302
    venue = VenueSettings.objects.get(pk=1)
    response = admin_client.post(
        reverse("admin:bookings_venuesettings_change", args=[1]),
        {
            "name": venue.name,
            "contact_email": "team@example.com",
            "phone": "",
            "address": venue.address,
            "hero_heading": venue.hero_heading,
            "pricing_intro": "A plan built around your guests.",
            "pricing_note": venue.pricing_note,
        },
    )
    assert response.status_code == 302
    html = client.get("/packages/").content.decode()
    assert "Evening wedding" in html and "$4,200" in html
    assert "Confirmed rental inclusion" in html
    assert "A plan built around your guests." in html
    assert "team@example.com" in html
    package.refresh_from_db()
    package.is_published = False
    package.save()
    assert "Evening wedding" not in client.get("/packages/").content.decode()
