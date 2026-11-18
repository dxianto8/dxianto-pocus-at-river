"""Picking a date updates the calendar and the "Your date" card in place; "Add your details"
then slides the page down to the request form."""

import re
from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

from bookings.models import Booking

# Start recording window.scrollY on every animation frame (about 2 seconds' worth).
RECORD_SCROLL = """() => {
  window.__scrollYs = [];
  const tick = () => {
    window.__scrollYs.push(Math.round(window.scrollY));
    if (window.__scrollYs.length < 150) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}"""

# True once the form's top edge has settled just under the sticky header.
FORM_IN_VIEW = """() => {
  const r = document.getElementById('request').getBoundingClientRect();
  return Math.abs(r.top - 96) < 4;
}"""


def heading_for(day) -> str:
    return f"Request {day:%A, %B} {day.day}, {day.year}"


def date_link(page: Page, day):
    """The date number, which picks the whole day."""
    return page.get_by_test_id("calendar").locator(f'td[data-date="{day:%Y-%m-%d}"] a.day__full')


@pytest.fixture
def day():
    return timezone.localdate() + timedelta(days=20)


@pytest.fixture
def booking_page(page: Page, day, customer_login) -> Page:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"/book/?month={day:%Y-%m}")
    page.evaluate("window.__sameDocument = true")  # disappears if the page reloads
    return page


def scroll_positions_while_continuing(page: Page, day) -> tuple[int, int, list[int]]:
    date_link(page, day).click()
    expect(page.locator(".pick__go")).to_be_visible()
    start = page.evaluate("Math.round(window.scrollY)")
    page.evaluate(RECORD_SCROLL)
    page.get_by_role("link", name="Add your details").click()
    page.wait_for_function(FORM_IN_VIEW)
    end = page.evaluate("Math.round(window.scrollY)")
    return start, end, page.evaluate("window.__scrollYs")


class TestPickingADate:
    def test_form_appears_without_reloading_the_page(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        expect(booking_page.get_by_role("heading", name=heading_for(day))).to_be_visible()
        assert booking_page.evaluate("window.__sameDocument") is True
        assert f"date={day:%Y-%m-%d}" in booking_page.url
        selected = booking_page.get_by_test_id("calendar").locator(
            f'td[data-date="{day:%Y-%m-%d}"]'
        )
        expect(selected).to_have_class(re.compile(r"\bday--selected\b"))

    def test_picking_keeps_the_calendar_in_view_and_fills_in_the_card(
        self, booking_page: Page, day
    ):
        start = booking_page.evaluate("Math.round(window.scrollY)")
        date_link(booking_page, day).click()
        card = booking_page.get_by_role("complementary", name="Your date")
        expect(card.get_by_role("heading", name=f"{day:%A}")).to_be_visible()
        expect(card.locator(".pick__half.is-chosen")).to_have_count(2)  # full day: both halves
        assert booking_page.evaluate("Math.round(window.scrollY)") == start

    def test_page_slides_smoothly_down_to_the_form(self, booking_page: Page, day):
        start, end, positions = scroll_positions_while_continuing(booking_page, day)
        assert end > start
        in_between = {y for y in positions if start < y < end}
        assert len(in_between) >= 3, f"expected a gradual scroll, got {positions}"

    def test_reduced_motion_jumps_straight_to_the_form(self, page: Page, day, customer_login):
        page.emulate_media(reduced_motion="reduce")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"/book/?month={day:%Y-%m}")
        start, end, positions = scroll_positions_while_continuing(page, day)
        assert end > start
        assert len({y for y in positions if start < y < end}) <= 1

    def test_keyboard_focus_follows_the_choice_then_the_form(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        expect(booking_page.locator(".pick__when")).to_be_focused()
        booking_page.get_by_role("link", name="Add your details").click()
        expect(booking_page.get_by_role("heading", name=heading_for(day))).to_be_focused()

    def test_back_button_returns_to_the_calendar_without_a_date(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        expect(booking_page.get_by_role("heading", name=heading_for(day))).to_be_visible()
        booking_page.go_back()
        expect(booking_page).not_to_have_url(re.compile("date="))
        expect(
            booking_page.get_by_role("heading", name=re.compile(r"^Request \w+day,"))
        ).to_have_count(0)

    def test_request_can_be_sent_from_the_form_that_slid_in(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        booking_page.get_by_label("Your name").fill("Avery Jones")
        booking_page.get_by_label("Phone", exact=True).fill("630 555 0100")
        booking_page.get_by_label("Event type").select_option("wedding")
        booking_page.get_by_label("Number of guests").fill("120")
        booking_page.get_by_role("button", name="Send Request").click()
        expect(booking_page.get_by_role("heading", name="Request received")).to_be_visible()
        assert Booking.objects.get().event_date == day


def test_date_links_still_work_without_javascript(browser, base_url, day, customer_login, page):
    context = browser.new_context(
        java_script_enabled=False, base_url=base_url, storage_state=page.context.storage_state()
    )
    page = context.new_page()
    page.goto(f"/book/?month={day:%Y-%m}")
    date_link(page, day).click()
    expect(page.get_by_role("heading", name=heading_for(day))).to_be_visible()
    assert page.url.endswith("#your-date")
    expect(page.get_by_role("link", name="Add your details")).to_be_visible()
    context.close()
