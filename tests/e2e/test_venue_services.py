from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import expect

from bookings.models import (
    Booking,
    BookingQuestion,
    EventTypeOption,
    LoyaltyCredit,
    LoyaltyReward,
    VenueSettings,
    WalkthroughAppointment,
    WalkthroughSlot,
)


def test_configured_questionnaire_and_event_times(page, customer_login):
    venue, _ = VenueSettings.objects.get_or_create(pk=1)
    venue.require_event_times = True
    venue.save()
    kind, _ = EventTypeOption.objects.get_or_create(code="wedding", defaults={"label": "Wedding"})
    question = BookingQuestion.objects.create(
        label="What is most important to you?", kind="long", is_required=True
    )
    question.event_types.add(kind)
    day = timezone.localdate() + timedelta(days=20)
    page.goto(f"/book/?date={day:%Y-%m-%d}")
    expect(page.get_by_label(question.label, exact=True)).not_to_be_visible()
    page.get_by_label("Event type", exact=True).select_option("wedding")
    expect(page.get_by_label(question.label, exact=True)).to_be_visible()
    page.get_by_label("Number of guests", exact=True).fill("80")
    page.get_by_label("Start time", exact=True).fill("16:00")
    page.get_by_label("End time", exact=True).fill("22:00")
    page.get_by_label(question.label, exact=True).fill("Dinner with our families")
    page.get_by_role("button", name="Send request", exact=True).click()
    expect(page.get_by_role("heading", name="Request received")).to_be_visible()
    saved = Booking.objects.get()
    assert saved.start_time.hour == 16 and saved.end_time.hour == 22
    assert saved.questionnaire_answers[0]["answer"] == "Dinner with our families"


def test_walkthrough_can_be_requested_and_cancelled_in_workspace(page, customer_login):
    start = timezone.now() + timedelta(days=3)
    slot = WalkthroughSlot.objects.create(
        starts_at=start, ends_at=start + timedelta(minutes=45), is_published=True
    )
    page.goto("/account/walkthroughs/")
    page.get_by_label("Appointment time", exact=True).select_option(str(slot.pk))
    page.get_by_label("Anything to know before your visit?", exact=True).fill(
        "Discuss our ceremony"
    )
    page.get_by_role("button", name="Request this appointment").click()
    expect(page.get_by_role("heading", name="My walkthrough appointments")).to_be_visible()
    assert WalkthroughAppointment.objects.get().owner == customer_login
    page.get_by_role("button", name="Cancel appointment").click()
    assert WalkthroughAppointment.objects.get().status == "cancelled"
    expect(page.get_by_role("button", name="Request this appointment")).to_be_visible()


def test_loyalty_and_unavailable_payments_share_account_tabs(page, customer_login):
    venue, _ = VenueSettings.objects.get_or_create(pk=1)
    venue.loyalty_enabled = True
    venue.save()
    LoyaltyCredit.objects.create(owner=customer_login, points=100, reason="Venue credit")
    LoyaltyReward.objects.create(
        title="Venue reward",
        description="A published reward",
        points_required=75,
        is_published=True,
    )
    page.goto("/account/loyalty/")
    expect(page.locator(".loyalty-points")).to_have_text("100")
    page.get_by_role("button", name="Request reward").click()
    expect(page.locator(".loyalty-points")).to_have_text("25")
    page.get_by_role("navigation", name="Account sections").get_by_role(
        "link", name="Payments"
    ).click()
    expect(page.get_by_role("heading", name="Event payments", exact=True)).to_be_visible()
    expect(page.get_by_text("Not available yet", exact=True)).to_have_count(2)
    expect(page.locator('input[autocomplete="cc-number"]')).to_have_count(0)
