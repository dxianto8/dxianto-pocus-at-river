import re
from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

from bookings.models import Booking


def future(days: int):
    return timezone.localdate() + timedelta(days=days)


def calendar_cell(page: Page, day):
    return page.get_by_test_id("calendar").locator(f'td[data-date="{day:%Y-%m-%d}"]')


def open_month(page: Page, day):
    page.goto(f"/book/?month={day:%Y-%m}")


def request_date(page: Page, day, name="Avery Jones", email="avery@example.com"):
    open_month(page, day)
    calendar_cell(page, day).get_by_role("link").click()
    expect(
        page.get_by_role("heading", name=f"Request {day:%A, %B} {day.day}, {day.year}")
    ).to_be_visible()
    page.get_by_label("Your name").fill(name)
    page.get_by_label("Event type").select_option("wedding")
    page.get_by_label("Number of guests").fill("150")
    page.get_by_role("button", name="Send Request").click()


@pytest.mark.usefixtures("customer_login")
class TestVisitor:
    def test_book_your_date_button_leads_to_the_calendar(self, page: Page):
        page.goto("/")
        page.get_by_test_id("hero").get_by_role("link", name="Start planning").click()
        expect(page.get_by_role("heading", level=1, name="Book Your Date")).to_be_visible()
        expect(page.get_by_test_id("calendar")).to_be_visible()

    def test_request_a_date_then_see_it_on_hold(self, page: Page):
        day = future(21)
        request_date(page, day)

        expect(page.get_by_role("heading", name="Thank You")).to_be_visible()
        expect(page.get_by_text(f"{day:%A, %B} {day.day}, {day.year}")).to_be_visible()
        assert Booking.objects.get().status == Booking.Status.PENDING

        open_month(page, day)
        cell = calendar_cell(page, day)
        expect(cell).to_have_attribute("data-state", "on_hold")
        expect(cell.get_by_text("On hold")).to_be_visible()
        expect(cell.get_by_role("link")).to_have_count(0)

    def test_same_date_cannot_be_requested_twice(self, page: Page, browser, base_url):
        day = future(22)
        open_month(page, day)
        calendar_cell(page, day).get_by_role("link").click()

        # Someone else requests the same date in another browser while this form is open.
        other = browser.new_page(base_url=base_url)
        other.goto("/account/login/")
        other.get_by_label("Username", exact=True).fill("eventguest")
        other.get_by_label("Password", exact=True).fill("correct-horse-battery-staple")
        other.get_by_role("button", name="Log in", exact=True).click()
        request_date(other, day, name="Someone Else", email="else@example.com")
        other.close()

        page.get_by_label("Your name").fill("Avery Jones")
        page.get_by_label("Event type").select_option("corporate")
        page.get_by_label("Number of guests").fill("60")
        page.get_by_role("button", name="Send Request").click()

        expect(page.get_by_role("alert")).to_contain_text("no longer available")
        assert Booking.objects.count() == 1


class TestAdmin:
    def test_admin_requires_login(self, page: Page):
        page.goto("/admin/bookings/booking/calendar/")
        expect(page).to_have_url(
            re.compile(r"/admin/login/\?next=/admin/bookings/booking/calendar/$")
        )
        page.get_by_label("Username").fill("nobody")
        page.get_by_label("Password").fill("wrong-password")
        page.get_by_role("button", name="Log in").click()
        expect(page.get_by_text("Please enter the correct username and password")).to_be_visible()

    def test_confirm_a_request_marks_the_date_booked(self, admin_page: Page):
        day = future(23)
        Booking.objects.create(
            event_date=day,
            name="Morgan Riley",
            email="m@example.com",
            event_type="wedding",
            guest_count=90,
        )
        admin_page.goto("/admin/bookings/booking/")
        admin_page.get_by_role("row", name="Morgan Riley").get_by_role("checkbox").check()
        admin_page.get_by_role("combobox", name="Action").select_option("confirm")
        admin_page.get_by_role("button", name="Run").click()
        expect(admin_page.get_by_text("Confirmed 1 booking(s).")).to_be_visible()

        open_month(admin_page, day)
        expect(calendar_cell(admin_page, day)).to_have_attribute("data-state", "booked")

    def test_decline_a_request_frees_the_date(self, admin_page: Page):
        day = future(24)
        Booking.objects.create(
            event_date=day,
            name="Jordan Price",
            email="j@example.com",
            event_type="other",
            guest_count=30,
        )
        admin_page.goto("/admin/bookings/booking/")
        admin_page.get_by_role("row", name="Jordan Price").get_by_role("checkbox").check()
        admin_page.get_by_role("combobox", name="Action").select_option("decline")
        admin_page.get_by_role("button", name="Run").click()

        open_month(admin_page, day)
        expect(calendar_cell(admin_page, day)).to_have_attribute("data-state", "available")

    def test_block_and_unblock_from_the_admin_calendar(self, admin_page: Page):
        day = future(25)
        label = f"{day:%B} {day.day}, {day.year}"
        admin_page.goto(f"/admin/bookings/booking/calendar/?month={day:%Y-%m}")
        admin_page.get_by_role("button", name=f"Block {label}").click()
        expect(admin_page.get_by_text(f"Blocked {day:%a %d %b %Y}.")).to_be_visible()

        open_month(admin_page, day)
        expect(calendar_cell(admin_page, day)).to_have_attribute("data-state", "booked")

        admin_page.goto(f"/admin/bookings/booking/calendar/?month={day:%Y-%m}")
        admin_page.get_by_role("button", name=f"Unblock {label}").click()
        open_month(admin_page, day)
        expect(calendar_cell(admin_page, day)).to_have_attribute("data-state", "available")
