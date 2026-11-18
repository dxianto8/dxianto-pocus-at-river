import base64
import hashlib
import hmac
import json
from datetime import UTC, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from bookings.email_backend import SendGridBackend
from bookings.forms import BookingEditForm, BookingRequestForm
from bookings.models import (
    Booking,
    BookingQuestion,
    CateringItem,
    EventFeedback,
    EventPackage,
    EventTypeOption,
    LoyaltyCredit,
    LoyaltyReward,
    PackageOffer,
    RecentEvent,
    RewardRedemption,
    ScheduledNotification,
    VenueSettings,
    WalkthroughAppointment,
    WalkthroughSlot,
)
from bookings.notifications import dispatch_notifications, enqueue, morning, send_sms
from bookings.offering_views import award_loyalty, loyalty_balance
from bookings.services import profile_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def customer(client):
    user = get_user_model().objects.create_user(
        "venueguest", "guest@example.com", "River-Day-2026!"
    )
    client.force_login(user)
    return user


def day(offset=0):
    return timezone.localdate() + timedelta(days=offset)


def booking(owner, **kwargs):
    return Booking.objects.create(
        owner=owner,
        event_date=kwargs.pop("event_date", day(20)),
        name="Guest",
        email=owner.email,
        event_type="wedding",
        guest_count=70,
        **kwargs,
    )


def payload(**kwargs):
    return {
        "event_date": day(20),
        "name": "Guest",
        "email": "guest@example.com",
        "phone": "630 555 0100",
        "event_type": "wedding",
        "guest_count": 70,
        **kwargs,
    }


def slot():
    start = morning(day(2))
    return WalkthroughSlot.objects.create(
        starts_at=start, ends_at=start + timedelta(minutes=45), is_published=True
    )


class TestQuestionnaire:
    def test_times_can_be_required_by_admin_and_must_be_in_order(self, customer):
        venue = VenueSettings.objects.get(pk=1)
        venue.require_event_times = True
        venue.save()
        form = BookingRequestForm(payload(), user=customer)
        assert not form.is_valid()
        assert "start_time" in form.errors and "end_time" in form.errors
        form = BookingRequestForm(payload(start_time="17:00", end_time="16:00"), user=customer)
        assert not form.is_valid() and "end_time" in form.errors
        form = BookingRequestForm(payload(start_time="16:00", end_time="22:00"), user=customer)
        assert form.is_valid(), form.errors
        assert form.save().start_time == time(16)

    def test_custom_event_types_and_conditional_questions_are_server_validated(self, customer):
        kind = EventTypeOption.objects.create(code="book-launch", label="Book launch")
        question = BookingQuestion.objects.create(label="Author name", is_required=True)
        question.event_types.add(kind)
        form = BookingRequestForm(payload(event_type=kind.code), user=customer)
        assert not form.is_valid() and f"question_{question.pk}" in form.errors
        form = BookingRequestForm(
            payload(event_type=kind.code, **{f"question_{question.pk}": "A. Reader"}), user=customer
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.get_event_type_display() == "Book launch"
        assert saved.questionnaire_answers[0]["answer"] == "A. Reader"
        question.label = "Changed label"
        question.save()
        saved.refresh_from_db()
        assert saved.questionnaire_answers[0]["question"] == "Author name"

    def test_questions_for_other_event_types_are_not_required_or_saved(self, customer):
        kind = EventTypeOption.objects.get(code="corporate")
        question = BookingQuestion.objects.create(label="Company", is_required=True)
        question.event_types.add(kind)
        form = BookingRequestForm(payload(**{f"question_{question.pk}": "forged"}), user=customer)
        assert form.is_valid(), form.errors
        assert form.save().questionnaire_answers == []

    def test_unknown_or_inactive_type_is_rejected(self, customer):
        EventTypeOption.objects.filter(code="wedding").update(is_active=False)
        form = BookingRequestForm(payload(), user=customer)
        assert not form.is_valid() and "event_type" in form.errors

    def test_archived_type_can_still_be_used_when_editing_existing_booking(self, customer):
        saved = booking(customer)
        EventTypeOption.objects.filter(code="wedding").update(is_active=False)
        form = BookingEditForm(payload(), instance=saved)
        assert form.is_valid(), form.errors


class TestOffersAndContent:
    def test_active_best_offer_and_snapshot_do_not_change_old_requests(self, customer):
        package = EventPackage.objects.get(slug="wedding")
        package.price = 1000
        package.save()
        offer = PackageOffer.objects.create(
            package=package,
            title="Season offer",
            percent_off=10,
            starts_on=day(-1),
            ends_on=day(2),
            terms="Proposal required",
            is_published=True,
        )
        PackageOffer.objects.create(
            package=package,
            title="Smaller offer",
            amount_off=25,
            starts_on=day(-1),
            ends_on=day(2),
            terms="Proposal required",
            is_published=True,
        )
        assert package.effective_price == Decimal("900.00")
        form = BookingRequestForm(payload(package=package.pk), user=customer)
        assert form.is_valid(), form.errors
        saved = form.save()
        offer.percent_off = 20
        offer.save()
        assert package.effective_price == Decimal("800.00")
        assert saved.price_snapshot == "From $900 per event"

    def test_invalid_offer_rejected_and_expired_offer_hidden(self):
        package = EventPackage.objects.get(slug="wedding")
        offer = PackageOffer(
            package=package,
            title="Invalid",
            percent_off=20,
            amount_off=10,
            ends_on=day(1),
            terms="Terms",
        )
        with pytest.raises(ValidationError):
            offer.full_clean()
        package.price = 300
        package.save()
        PackageOffer.objects.create(
            package=package,
            title="Expired",
            percent_off=50,
            starts_on=day(-4),
            ends_on=day(-1),
            is_published=True,
        )
        assert package.effective_price == 300

    def test_only_published_menu_items_and_recent_events_appear(self, client):
        CateringItem.objects.create(title="Draft menu", description="Private", is_published=False)
        CateringItem.objects.create(
            title="Seasonal dinner", description="Shared table", price=40, is_published=True
        )
        assert b"Seasonal dinner" in client.get("/catering/").content
        assert b"Draft menu" not in client.get("/catering/").content
        RecentEvent.objects.create(
            title="Private event", event_date=day(-2), summary="Private", category="Gathering"
        )
        RecentEvent.objects.create(
            title="Published gathering",
            event_date=day(-2),
            summary="An approved story",
            category="Gathering",
            is_published=True,
        )
        assert b"Published gathering" in client.get("/recent-events/").content
        assert b"Private event" not in client.get("/recent-events/").content
        assert b"Published gathering" in client.get("/").content


class TestWalkthroughs:
    def test_request_confirm_cancel_and_slot_reopens(self, client, customer, mailoutbox):
        available = slot()
        response = client.post(
            "/walkthroughs/", {"slot": available.pk, "notes": "Discuss a wedding"}
        )
        assert response.status_code == 302
        appointment = WalkthroughAppointment.objects.get()
        assert appointment.owner == customer and appointment.status == "pending"
        assert len(mailoutbox) == 2
        assert not client.get("/walkthroughs/").context["has_slots"]
        client.post(reverse("accounts:cancel_walkthrough", args=[appointment.pk]))
        assert client.get("/walkthroughs/").context["has_slots"]

    def test_slot_database_constraint_and_other_customer_cannot_cancel(self, client, customer):
        available = slot()
        appointment = WalkthroughAppointment.objects.create(owner=customer, slot=available)
        with pytest.raises(IntegrityError), transaction.atomic():
            WalkthroughAppointment.objects.create(owner=customer, slot=available)
        other = get_user_model().objects.create_user(
            "other", "other@example.com", "River-Day-2026!"
        )
        client.force_login(other)
        assert (
            client.post(reverse("accounts:cancel_walkthrough", args=[appointment.pk])).status_code
            == 404
        )
        assert not client.get("/account/walkthroughs/").context["appointments"].exists()

    def test_hidden_or_past_slots_cannot_be_requested(self, client, customer):
        available = slot()
        available.is_published = False
        available.save()
        response = client.post("/walkthroughs/", {"slot": available.pk})
        assert response.status_code == 200
        assert not WalkthroughAppointment.objects.exists()

    def test_anonymous_requests_require_signup(self, client):
        response = client.post("/walkthroughs/", {"slot": slot().pk})
        assert response.status_code == 302 and "/account/signup/" in response.url
        assert not WalkthroughAppointment.objects.exists()


class TestLoyaltyAndFeedback:
    def configure(self):
        venue = VenueSettings.objects.get(pk=1)
        venue.loyalty_enabled = True
        venue.loyalty_start_date = day(-30)
        venue.loyalty_points_per_event = 100
        venue.save()
        return venue

    def test_credits_are_once_only_for_completed_confirmed_owned_events(self, customer):
        self.configure()
        booking(customer, event_date=day(-2), status="confirmed")
        booking(customer, event_date=day(-3), status="cancelled")
        booking(customer, event_date=day(2), status="confirmed")
        award_loyalty(customer)
        award_loyalty(customer)
        assert LoyaltyCredit.objects.filter(owner=customer).count() == 1
        assert loyalty_balance(customer) == 100

    def test_redemption_reserves_points_and_decline_releases_them(self, client, customer):
        self.configure()
        LoyaltyCredit.objects.create(owner=customer, points=100, reason="Staff credit")
        reward = LoyaltyReward.objects.create(
            title="Venue reward",
            description="Approved reward",
            points_required=80,
            is_published=True,
        )
        path = reverse("accounts:redeem_reward", args=[reward.pk])
        client.post(path)
        client.post(path)
        assert RewardRedemption.objects.count() == 1
        assert loyalty_balance(customer) == 20
        redemption = RewardRedemption.objects.get()
        redemption.status = "declined"
        redemption.save()
        assert loyalty_balance(customer) == 100

    def test_feedback_is_owner_only_for_completed_confirmed_events(self, client, customer):
        completed = booking(customer, event_date=day(-1), status="confirmed")
        url = reverse("accounts:feedback", args=[completed.pk])
        assert (
            client.post(url, {"rating": 2, "comments": "Useful private feedback"}).status_code
            == 302
        )
        assert EventFeedback.objects.get().rating == 2
        venue = VenueSettings.objects.get(pk=1)
        venue.review_url = "https://example.com/reviews"
        venue.save()
        assert (
            venue.review_url.encode() in client.get(url).content
        )  # No rating-gating of public reviews.
        client.post(url, {"rating": 5, "comments": "Updated"})
        assert EventFeedback.objects.count() == 1
        other = get_user_model().objects.create_user(
            "stranger", "stranger@example.com", "River-Day-2026!"
        )
        client.force_login(other)
        assert client.get(url).status_code == 404

    def test_future_or_cancelled_event_has_no_feedback_form(self, client, customer):
        upcoming = booking(customer, status="confirmed")
        assert client.get(reverse("accounts:feedback", args=[upcoming.pk])).status_code == 404


class TestNotifications:
    def configure(self, customer):
        venue = VenueSettings.objects.get(pk=1)
        venue.automated_email_enabled = venue.automated_sms_enabled = True
        venue.save()
        profile = profile_for(customer)
        profile.sms_reminders = profile.feedback_updates = True
        profile.phone = "+13125550123"
        profile.save()
        return venue

    def test_job_is_idempotent_and_respects_sms_opt_out(self, customer, mailoutbox):
        self.configure(customer)
        booking(customer, event_date=day(1), status="confirmed")
        now = morning(day()) + timedelta(hours=2)
        with patch("bookings.notifications.send_sms", return_value="sms-id") as sms:
            assert dispatch_notifications(now)["sent"] == 2
            assert dispatch_notifications(now)["sent"] == 0
            assert sms.call_count == 1
        assert len(mailoutbox) == 1
        assert ScheduledNotification.objects.filter(status="sent").count() == 2

    def test_queued_notification_rechecks_booking_state_and_consent(self, customer):
        venue = self.configure(customer)
        saved = booking(customer, event_date=day(1), status="confirmed")
        now = morning(day()) + timedelta(hours=2)
        enqueue(
            customer, "event", morning(day()), saved.event_date, booking=saved, now=now, venue=venue
        )
        saved.status = "cancelled"
        saved.save()
        with patch("bookings.notifications.send_sms") as sms:
            assert dispatch_notifications(now)["skipped"] == 2
            sms.assert_not_called()

    def test_provider_failure_retries_without_marking_as_sent(self, customer):
        self.configure(customer)
        profile = profile_for(customer)
        profile.email_updates = False
        profile.save()
        booking(customer, event_date=day(1), status="confirmed")
        now = morning(day()) + timedelta(hours=2)
        with patch("bookings.notifications.send_sms", side_effect=RuntimeError("offline")):
            assert dispatch_notifications(now)["failed"] == 1
        record = ScheduledNotification.objects.get()
        assert record.status == "failed" and record.attempts == 1 and record.sent_at is None
        with patch("bookings.notifications.send_sms", return_value="accepted"):
            assert dispatch_notifications(now + timedelta(minutes=6))["sent"] == 1
        record.refresh_from_db()
        assert record.attempts == 2 and record.provider_id == "accepted"

    def test_post_event_invitation_requires_feedback_consent(self, customer, mailoutbox):
        self.configure(customer)
        booking(customer, event_date=day(-1), status="confirmed")
        profile = profile_for(customer)
        profile.feedback_updates = False
        profile.save()
        assert dispatch_notifications(morning(day()) + timedelta(hours=2))["sent"] == 0
        assert not mailoutbox
        profile.feedback_updates = True
        profile.save()
        with patch("bookings.notifications.send_sms", return_value="accepted"):
            assert dispatch_notifications(morning(day()) + timedelta(hours=2))["sent"] == 2
        assert "/feedback/" in mailoutbox[0].body

    @override_settings(CRON_SECRET="test-cron-secret")
    def test_cron_endpoint_is_authenticated(self, client):
        assert client.get("/notifications/dispatch/").status_code == 403
        assert (
            client.get("/notifications/dispatch/", HTTP_AUTHORIZATION="Bearer wrong").status_code
            == 403
        )
        assert (
            client.get(
                "/notifications/dispatch/", HTTP_AUTHORIZATION="Bearer test-cron-secret"
            ).status_code
            == 200
        )

    @override_settings(TWILIO_AUTH_TOKEN="signing-key")
    def test_signed_sms_stop_webhook_updates_consent(self, client, customer):
        self.configure(customer)
        path = "/notifications/sms/"
        data = {"From": "+13125550123", "Body": "STOP"}
        assert client.post(path, data).status_code == 403
        value = "http://testserver" + path + "".join(key + data[key] for key in sorted(data))
        signature = base64.b64encode(
            hmac.new(b"signing-key", value.encode(), hashlib.sha1).digest()
        ).decode()
        assert client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature).status_code == 200
        assert not profile_for(customer).sms_reminders

    def test_sms_opt_in_requires_an_international_number(self, client, customer):
        response = client.post(
            "/account/settings/",
            {"first_name": "Guest", "email": customer.email, "phone": "123", "sms_reminders": "on"},
        )
        assert response.status_code == 200
        assert "phone" in response.context["form"].errors


def test_sendgrid_payload_and_failed_delivery():
    response = MagicMock()
    response.__enter__.return_value.status = 202
    message = EmailMultiAlternatives(
        "Subject",
        "Plain text",
        "Venue <venue@example.com>",
        ["guest@example.com"],
        bcc=["private@example.com"],
    )
    message.attach_alternative("<p>HTML</p>", "text/html")
    with patch("bookings.email_backend.urlopen", return_value=response) as api:
        assert SendGridBackend(api_key="test-key").send_messages([message]) == 1
        request = api.call_args.args[0]
        payload = json.loads(request.data)
        assert request.full_url == "https://api.sendgrid.com/v3/mail/send"
        assert payload["personalizations"][0]["bcc"] == [{"email": "private@example.com"}]
        assert payload["content"][1]["type"] == "text/html"
        assert "test-key" in request.headers["Authorization"]
    response.__enter__.return_value.status = 400
    with (
        patch("bookings.email_backend.urlopen", return_value=response),
        pytest.raises(RuntimeError),
    ):
        SendGridBackend(api_key="test-key").send_messages([message])


@override_settings(
    TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="test-key", TWILIO_FROM_NUMBER="+13125550000"
)
def test_twilio_payload():
    response = MagicMock()
    response.__enter__.return_value.status = 201
    response.__enter__.return_value.read.return_value = b'{"sid":"SMaccepted"}'
    with patch("bookings.notifications.urlopen", return_value=response) as api:
        assert send_sms("+13125550123", "Reminder") == "SMaccepted"
        assert "To=%2B13125550123" in api.call_args.args[0].data.decode()


def test_archived_event_type_hides_packages_but_preserves_existing_selection(customer):
    package = EventPackage.objects.get(slug="wedding")
    saved = booking(customer, package=package)
    EventTypeOption.objects.filter(code="wedding").update(is_active=False)
    assert not EventPackage.objects.published().filter(pk=package.pk).exists()
    assert (
        not BookingRequestForm(user=customer)
        .fields["package"]
        .queryset.filter(pk=package.pk)
        .exists()
    )
    form = BookingEditForm(payload(package=package.pk), instance=saved)
    assert form.is_valid(), form.errors


def test_sendgrid_is_used_through_django_mailer_configuration():
    from django.core.mail import send_mail

    response = MagicMock()
    response.__enter__.return_value.status = 202
    config = {
        "default": {
            "BACKEND": "bookings.email_backend.SendGridBackend",
            "OPTIONS": {"api_key": "configured-test-key"},
        }
    }
    with (
        override_settings(MAILERS=config),
        patch("bookings.email_backend.urlopen", return_value=response) as api,
    ):
        assert (
            send_mail("Status update", "Your event", "sender@example.com", ["guest@example.com"])
            == 1
        )
        assert api.call_args.args[0].headers["Authorization"] == "Bearer configured-test-key"


def test_custom_question_help_is_plain_text_in_customer_forms(client, customer):
    question = BookingQuestion.objects.create(
        label="A question", help_text='<script>alert("unsafe")</script>'
    )
    response = client.get(f"/book/?date={day(20):%Y-%m-%d}")
    assert response.status_code == 200
    assert b"&lt;script&gt;" in response.content
    assert b'<script>alert("unsafe")</script>' not in response.content
    assert question.label.encode() in response.content


def test_calendar_export_uses_requested_chicago_times(client, customer):
    from datetime import datetime

    saved = booking(customer, start_time=time(16), end_time=time(22))
    response = client.get(reverse("accounts:booking_ics", args=[saved.pk]))
    starts = timezone.make_aware(datetime.combine(saved.event_date, saved.start_time))
    expected = f"DTSTART:{starts.astimezone(UTC):%Y%m%dT%H%M%SZ}"
    assert expected.encode() in response.content
    assert b"DTSTART;VALUE=DATE" not in response.content
