from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bookings.calendar import add_months
from bookings.models import Booking, WalkthroughRequest
from bookings.models import Testimonial as GuestTestimonial

pytestmark = pytest.mark.django_db


def tour_data(**overrides):
    return {
        "name": "Avery Jones",
        "email": "avery@example.com",
        "phone": "",
        "preferred_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
        "preferred_time": "afternoon",
        "event_type": "wedding",
        "message": "Please let us know about step-free access.",
        "contact_consent": "on",
        "website": "",
        **overrides,
    }


@pytest.mark.parametrize("url", ["/", "/venue/", "/walk-throughs/", "/book/"])
def test_public_pages_have_navigation_and_venue_contact(client, url):
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    for path in ["/venue/", "/walk-throughs/", "/book/"]:
        assert f'href="{path}"' in html
    assert 'aria-current="page"' in html
    assert "events@pocusatriver.com" in html
    assert "100 S. River Street" in html


def test_walkthrough_saves_separately_without_holding_event_date(client):
    data = tour_data(status="confirmed", admin_note="Untrusted input")
    Booking.objects.create(event_date=data["preferred_date"], status=Booking.Status.BLOCKED)
    response = client.post(reverse("walkthrough"), data)
    assert response.status_code == 302
    assert response.url == reverse("walkthrough_requested")
    tour = WalkthroughRequest.objects.get()
    assert tour.name == data["name"]
    assert tour.message == data["message"]
    assert tour.status == WalkthroughRequest.Status.PENDING
    assert tour.admin_note == ""
    assert tour.contact_consent_at is not None
    assert Booking.objects.count() == 1
    # More than one person may ask to visit on the same day; staff arrange actual times.
    client.post(reverse("walkthrough"), tour_data(email="other@example.com"))
    assert WalkthroughRequest.objects.count() == 2


def test_walkthrough_contact_checkbox_starts_unchecked(client):
    response = client.get(reverse("walkthrough"))
    form = response.context["form"]
    assert form["contact_consent"].value() is False
    assert "checked" not in str(form["contact_consent"])


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"contact_consent": ""}, "contact_consent"),
        ({"email": "not-an-email"}, "email"),
        ({"name": ""}, "name"),
        ({"preferred_time": "midnight"}, "preferred_time"),
        ({"preferred_date": "not-a-date"}, "preferred_date"),
        (
            {"preferred_date": (timezone.localdate() - timedelta(days=1)).isoformat()},
            "preferred_date",
        ),
        (
            {
                "preferred_date": (
                    add_months(timezone.localdate(), 24) + timedelta(days=1)
                ).isoformat()
            },
            "preferred_date",
        ),
    ],
)
def test_invalid_walkthrough_keeps_values_and_saves_nothing(client, changes, field):
    response = client.post(reverse("walkthrough"), tour_data(**changes))
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert response.context["form"]["message"].value() == tour_data()["message"]
    assert not WalkthroughRequest.objects.exists()
    assert not Booking.objects.exists()


def test_walkthrough_spam_trap_does_not_save(client):
    response = client.post(reverse("walkthrough"), tour_data(website="https://spam.example"))
    assert response.status_code == 302
    assert not WalkthroughRequest.objects.exists()


def test_walkthrough_requires_csrf_token():
    response = Client(enforce_csrf_checks=True).post(reverse("walkthrough"), tour_data())
    assert response.status_code == 403
    assert not WalkthroughRequest.objects.exists()


def test_contact_details_are_not_public(client):
    client.post(reverse("walkthrough"), tour_data())
    for url in ["/", "/venue/", "/walk-throughs/", "/book/", "/walk-throughs/requested/"]:
        html = client.get(url).content.decode()
        assert "avery@example.com" not in html
        assert "Avery Jones" not in html
    assert client.get(reverse("admin:bookings_walkthroughrequest_changelist")).status_code == 302


def test_staff_can_review_and_confirm_a_visit(admin_client, client):
    client.post(reverse("walkthrough"), tour_data())
    tour = WalkthroughRequest.objects.get()
    response = admin_client.get(reverse("admin:bookings_walkthroughrequest_changelist"))
    assert b"Avery Jones" in response.content
    response = admin_client.post(
        reverse("admin:bookings_walkthroughrequest_change", args=[tour.pk]),
        {**tour_data(), "status": "confirmed", "admin_note": "Arranged directly with guest."},
    )
    assert response.status_code == 302
    tour.refresh_from_db()
    assert tour.status == WalkthroughRequest.Status.CONFIRMED
    assert not Booking.objects.exists()


def test_only_published_reviews_with_permission_appear(client):
    GuestTestimonial.objects.create(quote="A private draft.", attribution="Private Guest")
    GuestTestimonial.objects.create(
        quote="No permission yet.", attribution="Unapproved Guest", is_published=True
    )
    approved = GuestTestimonial.objects.create(
        quote="Our <special> day.",
        attribution="Guest & Partner",
        event_label="Wedding",
        permission_granted=True,
        is_published=True,
    )
    html = client.get("/").content.decode()
    assert "Private Guest" not in html
    assert "Unapproved Guest" not in html
    assert "Our &lt;special&gt; day." in html
    assert "Guest &amp; Partner" in html
    approved.permission_granted = False
    with pytest.raises(ValidationError):
        approved.full_clean()


def test_empty_testimonials_invite_stories_without_fake_reviews(client):
    html = client.get("/").content.decode()
    assert "Share your story" in html
    assert 'data-testimonial role="group"' not in html
