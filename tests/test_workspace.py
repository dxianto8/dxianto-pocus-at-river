"""What a signed-in customer can do with their own event: change it, cancel it, talk to the
venue, plan it, and share files. Every action is limited to the event's owner."""

from datetime import time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from bookings import services
from bookings.models import Booking, ChecklistItem, Document, Message

pytestmark = pytest.mark.django_db
PASSWORD = "River-Planning-2026!"


def day(offset):
    return timezone.localdate() + timedelta(days=offset)


@pytest.fixture
def customer(client):
    user = get_user_model().objects.create_user(
        "riverguest", "guest@example.com", PASSWORD, first_name="Avery"
    )
    client.force_login(user)
    return user


@pytest.fixture
def stranger():
    return get_user_model().objects.create_user("stranger", "stranger@example.com", PASSWORD)


def make_booking(owner, **overrides):
    values = {
        "event_date": day(200),
        "name": "Avery",
        "email": owner.email,
        "event_type": "wedding",
        "guest_count": 80,
        **overrides,
    }
    return Booking.objects.create(owner=owner, **values)


def url(name, booking, *args):
    return reverse(f"accounts:{name}", args=[booking.pk, *args])


def edit_data(booking, **overrides):
    return {
        "event_date": booking.event_date.isoformat(),
        "name": booking.name,
        "phone": "",
        "event_type": booking.event_type,
        "package": "",
        "guest_count": booking.guest_count,
        "message": "",
        **overrides,
    }


class TestNewRequest:
    def test_gets_a_starting_checklist_a_history_line_and_tells_the_venue(
        self, client, customer, mailoutbox
    ):
        client.post(
            "/book/",
            {
                "event_date": day(200).isoformat(),
                "name": "Avery",
                "event_type": "wedding",
                "guest_count": "80",
            },
        )
        booking = Booking.objects.get()
        assert booking.checklist.count() == len(services.STARTING_CHECKLIST["wedding"])
        assert booking.activity.get().text == "You requested this date."
        assert mailoutbox[0].to == ["events@pocusatriver.com"]
        assert "New request" in mailoutbox[0].subject

    def test_checklist_steps_that_are_already_late_get_no_due_date(self, customer):
        booking = make_booking(customer, event_date=day(10))
        services.seed_checklist(booking)
        assert not booking.checklist.filter(due_date__lt=timezone.localdate()).exists()
        assert booking.checklist.filter(due_date=None).exists()


class TestChangingARequest:
    def test_owner_changes_details_and_moves_the_date(self, client, customer, mailoutbox):
        booking = make_booking(customer)
        services.seed_checklist(booking)
        first_due = booking.checklist.filter(due_date__isnull=False).first().due_date
        response = client.post(
            url("booking_edit", booking),
            edit_data(booking, event_date=day(207).isoformat(), guest_count=95),
        )
        assert response.url == url("booking_detail", booking)
        booking.refresh_from_db()
        assert (booking.event_date, booking.guest_count) == (day(207), 95)
        assert booking.status == Booking.Status.PENDING
        assert booking.checklist.filter(due_date__isnull=False).first().due_date == (
            first_due + timedelta(days=7)
        )
        assert "moved the request" in booking.activity.last().text
        assert "Request updated" in mailoutbox[0].subject

    def test_cannot_move_onto_a_taken_or_past_date(self, client, customer, stranger):
        booking = make_booking(customer)
        make_booking(stranger, event_date=day(30))
        for bad in (day(30), day(-1), day(365 * 3)):
            response = client.post(
                url("booking_edit", booking), edit_data(booking, event_date=bad.isoformat())
            )
            assert "event_date" in response.context["form"].errors
        booking.refresh_from_db()
        assert booking.event_date == day(200)

    def test_status_and_owner_cannot_be_set_through_the_form(self, client, customer, stranger):
        booking = make_booking(customer)
        client.post(
            url("booking_edit", booking),
            edit_data(booking, status="confirmed", owner=stranger.pk, admin_note="x"),
        )
        booking.refresh_from_db()
        assert booking.status == Booking.Status.PENDING
        assert booking.owner == customer and booking.admin_note == ""

    def test_confirmed_events_are_changed_by_message_not_by_form(self, client, customer):
        booking = make_booking(customer, status="confirmed")
        response = client.post(url("booking_edit", booking), edit_data(booking, guest_count=5))
        assert response.url == url("booking_messages", booking)
        booking.refresh_from_db()
        assert booking.guest_count == 80


class TestCancelling:
    @pytest.mark.parametrize("status", ["pending", "confirmed"])
    def test_owner_cancels_and_the_date_is_free_again(self, client, customer, status, mailoutbox):
        booking = make_booking(customer, status=status)
        assert client.get(url("booking_cancel", booking)).status_code == 200
        booking.refresh_from_db()
        assert booking.status == status  # looking at the page changes nothing
        client.post(url("booking_cancel", booking))
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CANCELLED
        assert not Booking.objects.active().filter(event_date=booking.event_date).exists()
        assert "Cancelled by customer" in mailoutbox[0].subject

    @pytest.mark.parametrize("status", ["declined", "cancelled"])
    def test_finished_requests_cannot_be_cancelled_again(self, client, customer, status):
        booking = make_booking(customer, status=status)
        client.post(url("booking_cancel", booking))
        booking.refresh_from_db()
        assert booking.status == status and not booking.activity.exists()

    def test_past_events_cannot_be_cancelled(self, client, customer):
        booking = make_booking(customer, status="confirmed", event_date=day(-3))
        client.post(url("booking_cancel", booking))
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED


class TestMessages:
    def test_customer_writes_and_venue_is_emailed(self, client, customer, mailoutbox):
        booking = make_booking(customer)
        client.post(url("booking_messages", booking), {"body": "Can we bring a band?"})
        message = booking.messages.get()
        assert (message.author, message.from_staff) == (customer, False)
        assert "Can we bring a band?" in mailoutbox[0].body

    def test_reading_the_thread_clears_the_unread_count(self, client, customer):
        booking = make_booking(customer)
        Message.objects.create(booking=booking, from_staff=True, body="Yes, until 11pm.")
        assert client.get(reverse("accounts:dashboard")).context["unread_messages"] == 1
        assert client.get(reverse("accounts:inbox")).context["rows"][0]["booking"].unread == 1
        assert b"Yes, until 11pm." in client.get(url("booking_messages", booking)).content
        assert client.get(reverse("accounts:dashboard")).context["unread_messages"] == 0

    def test_staff_reply_in_admin_reaches_the_customer(self, admin_client, customer, mailoutbox):
        booking = make_booking(customer)
        Message.objects.create(booking=booking, author=customer, body="Hello?")
        change = reverse("admin:bookings_booking_change", args=[booking.pk])
        page = admin_client.get(change)
        assert Message.objects.get().read_at is not None  # opening it marks it read for staff
        data = {}
        for formset in page.context["inline_admin_formsets"]:
            management = formset.formset.management_form
            for name in management.fields:
                data[f"{management.prefix}-{name}"] = management[name].value()
        form = page.context["adminform"].form
        data.update({name: form[name].value() or "" for name in form.fields})
        data.update({"messages-0-id": Message.objects.get().pk, "messages-0-booking": booking.pk})
        data.update({"messages-1-booking": booking.pk, "messages-1-body": "Hello Avery."})
        response = admin_client.post(change, data)
        assert response.status_code == 302, response.context["errors"]
        reply = booking.messages.last()
        assert reply.from_staff and reply.body == "Hello Avery."
        assert mailoutbox[-1].to == [customer.email]
        assert "Hello Avery." in mailoutbox[-1].body

    def test_customers_who_opt_out_get_no_email(self, customer, mailoutbox):
        booking = make_booking(customer)
        profile = services.profile_for(customer)
        profile.email_updates = False
        profile.save()
        services.notify_customer(booking, "Anything", ["text"])
        assert not mailoutbox


class TestStatusChangesByStaff:
    def test_confirming_in_admin_logs_and_emails_the_customer(
        self, admin_client, customer, mailoutbox
    ):
        booking = make_booking(customer)
        admin_client.post(
            reverse("admin:bookings_booking_changelist"),
            {"action": "confirm", "_selected_action": [booking.pk]},
        )
        assert booking.activity.get().text == "The venue confirmed the booking."
        assert mailoutbox[0].to == [customer.email]
        assert "confirmed" in mailoutbox[0].subject
        page = customer_page(customer, url("booking_detail", booking))
        assert "The venue confirmed the booking." in page


def customer_page(user, path):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client.get(path).content.decode()


class TestChecklistAndSchedule:
    def test_add_tick_untick_and_remove_a_task(self, client, customer):
        booking = make_booking(customer)
        client.post(url("booking_checklist", booking), {"title": "Order cake", "due_date": ""})
        item = booking.checklist.get()
        client.post(url("checklist_item", booking, item.pk))
        item.refresh_from_db()
        assert item.is_done
        client.post(url("checklist_item", booking, item.pk))
        item.refresh_from_db()
        assert not item.is_done
        client.post(url("checklist_item", booking, item.pk), {"action": "delete"})
        assert not booking.checklist.exists()

    def test_tasks_from_the_venue_can_be_ticked_but_not_removed(self, client, customer):
        booking = make_booking(customer)
        item = ChecklistItem.objects.create(booking=booking, title="Sign", from_staff=True)
        client.post(url("checklist_item", booking, item.pk), {"action": "delete"})
        assert booking.checklist.exists()

    def test_overdue_tasks_show_on_the_dashboard(self, client, customer):
        booking = make_booking(customer)
        ChecklistItem.objects.create(booking=booking, title="Send invitations", due_date=day(-2))
        attention = client.get(reverse("accounts:dashboard")).context["attention"]
        assert [(a["kind"], a["text"]) for a in attention] == [("overdue", "Send invitations")]

    def test_schedule_lines_are_kept_in_time_order(self, client, customer):
        booking = make_booking(customer)
        for when, title in [("18:30", "Dinner"), ("16:00", "Ceremony")]:
            client.post(url("booking_schedule", booking), {"time": when, "title": title})
        assert [i.title for i in booking.schedule.all()] == ["Ceremony", "Dinner"]
        first = booking.schedule.first()
        assert first.time == time(16, 0)
        client.post(url("schedule_item", booking, first.pk))
        assert booking.schedule.count() == 1


class TestDocuments:
    def upload(self, client, booking, name="plan.pdf", content=b"%PDF-1.4 floor plan"):
        return client.post(
            url("booking_documents", booking),
            {"title": "", "file": SimpleUploadedFile(name, content)},
        )

    def test_upload_download_and_remove(self, client, customer):
        booking = make_booking(customer)
        assert self.upload(client, booking).status_code == 302
        document = booking.documents.get()
        assert (document.title, document.content_type) == ("plan.pdf", "application/pdf")
        response = client.get(url("document", booking, document.pk))
        assert response.content == b"%PDF-1.4 floor plan"
        assert response["Content-Disposition"] == 'attachment; filename="plan.pdf"'
        assert response["X-Content-Type-Options"] == "nosniff"
        client.post(url("document", booking, document.pk))
        assert not booking.documents.exists()

    @pytest.mark.parametrize(
        "name,content",
        [("page.html", b"<script>"), ("big.pdf", b"x" * (Document.MAX_BYTES + 1)), ("e.pdf", b"")],
    )
    def test_refuses_other_file_types_oversized_and_empty_files(
        self, client, customer, name, content
    ):
        booking = make_booking(customer)
        response = self.upload(client, booking, name, content)
        assert "file" in response.context["form"].errors
        assert not booking.documents.exists()

    def test_documents_from_the_venue_are_flagged_new_and_cannot_be_removed(self, client, customer):
        booking = make_booking(customer)
        document = Document.objects.create(
            booking=booking,
            title="Proposal",
            filename="proposal.pdf",
            content_type="application/pdf",
            size=4,
            data=b"%PDF",
            from_staff=True,
        )
        attention = client.get(reverse("accounts:dashboard")).context["attention"]
        assert attention[0]["kind"] == "document"
        client.get(url("booking_documents", booking))
        assert not client.get(reverse("accounts:dashboard")).context["attention"]
        client.post(url("document", booking, document.pk))
        assert booking.documents.exists()


def test_calendar_file_describes_the_event(client, customer):
    booking = make_booking(customer, status="confirmed")
    response = client.get(url("booking_ics", booking))
    body = response.content.decode()
    assert response["Content-Type"].startswith("text/calendar")
    assert f"DTSTART;VALUE=DATE:{booking.event_date:%Y%m%d}" in body
    assert "STATUS:CONFIRMED" in body and "LOCATION:100 S. River Street\\, Aurora\\, IL" in body


def test_own_dates_are_marked_on_the_calendar(client, customer, stranger):
    mine = make_booking(customer, event_date=day(20))
    make_booking(stranger, event_date=day(21))
    response = client.get("/book/", {"month": f"{day(20):%Y-%m}"})
    assert list(response.context["mine"].values()) == [mine]
    assert url("booking_detail", mine).encode() in response.content


def test_home_page_shows_upcoming_saturdays_without_personal_details(client, stranger):
    saturday = day((5 - timezone.localdate().weekday()) % 7 + 7)
    make_booking(stranger, event_date=saturday, name="Secret Name", status="confirmed")
    response = client.get("/")
    states = {item["date"]: item["state"] for item in response.context["saturdays"]}
    assert states[saturday] == "booked" and len(states) == 8
    assert b"Secret Name" not in response.content


class TestProfile:
    def data(self, **overrides):
        return {
            "first_name": "Avery",
            "last_name": "Jones",
            "email": "guest@example.com",
            "phone": "630 555 0100",
            "email_updates": "on",
            "current_password": "",
            **overrides,
        }

    def test_name_and_phone_save_without_a_password(self, client, customer):
        assert client.post(reverse("accounts:settings"), self.data()).status_code == 302
        customer.refresh_from_db()
        assert customer.last_name == "Jones" and customer.profile.phone == "630 555 0100"

    def test_changing_email_needs_the_current_password(self, client, customer):
        new = self.data(email="new@example.com")
        response = client.post(reverse("accounts:settings"), new)
        assert "current_password" in response.context["form"].errors
        customer.refresh_from_db()
        assert customer.email == "guest@example.com"
        client.post(reverse("accounts:settings"), {**new, "current_password": PASSWORD})
        customer.refresh_from_db()
        assert customer.email == "new@example.com"


OWNER_ONLY = [
    ("booking_detail", "get"),
    ("booking_edit", "get"),
    ("booking_edit", "post"),
    ("booking_cancel", "post"),
    ("booking_ics", "get"),
    ("booking_messages", "post"),
    ("booking_checklist", "post"),
    ("booking_schedule", "post"),
    ("booking_documents", "post"),
]


@pytest.mark.parametrize("name,method", OWNER_ONLY)
def test_another_customers_event_is_not_found(client, customer, stranger, name, method):
    theirs = make_booking(stranger)
    response = getattr(client, method)(url(name, theirs), {"body": "x", "title": "x"})
    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.status == Booking.Status.PENDING
    assert not theirs.messages.exists() and not theirs.checklist.exists()


def test_another_customers_items_and_files_are_not_found(client, customer, stranger):
    theirs = make_booking(stranger)
    mine = make_booking(customer, event_date=day(100))
    item = ChecklistItem.objects.create(booking=theirs, title="Private")
    line = theirs.schedule.create(time=time(12, 0), title="Private")
    document = Document.objects.create(
        booking=theirs, title="Private", filename="p.pdf", content_type="application/pdf", data=b"x"
    )
    # Neither through their event, nor by pairing their item with my own event.
    for booking in (theirs, mine):
        assert client.post(url("checklist_item", booking, item.pk)).status_code == 404
        assert client.post(url("schedule_item", booking, line.pk)).status_code == 404
        assert client.get(url("document", booking, document.pk)).status_code == 404
        assert client.post(url("document", booking, document.pk)).status_code == 404
    assert Document.objects.count() == 1 and theirs.schedule.count() == 1


@pytest.mark.parametrize("name,method", OWNER_ONLY)
def test_workspace_actions_need_a_login(client, stranger, name, method):
    response = getattr(client, method)(url(name, make_booking(stranger)))
    assert response.status_code == 302 and response.url.startswith("/account/login/")
