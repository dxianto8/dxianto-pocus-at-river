"""Picking a date loads the request form in place and slides the page down to it."""

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
    return page.get_by_test_id("calendar").locator(f'td[data-date="{day:%Y-%m-%d}"] a')


@pytest.fixture
def day():
    return timezone.localdate() + timedelta(days=20)


@pytest.fixture
def booking_page(page: Page, day) -> Page:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"/book/?month={day:%Y-%m}")
    page.evaluate("window.__sameDocument = true")  # disappears if the page reloads
    return page


def scroll_positions_while_picking(page: Page, day) -> tuple[int, int, list[int]]:
    start = page.evaluate("Math.round(window.scrollY)")
    page.evaluate(RECORD_SCROLL)
    date_link(page, day).click()
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

    def test_page_slides_smoothly_down_to_the_form(self, booking_page: Page, day):
        start, end, positions = scroll_positions_while_picking(booking_page, day)
        assert end > start
        in_between = {y for y in positions if start < y < end}
        assert len(in_between) >= 3, f"expected a gradual scroll, got {positions}"

    def test_reduced_motion_jumps_straight_to_the_form(self, page: Page, day):
        page.emulate_media(reduced_motion="reduce")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"/book/?month={day:%Y-%m}")
        start, end, positions = scroll_positions_while_picking(page, day)
        assert end > start
        assert len({y for y in positions if start < y < end}) <= 1

    def test_keyboard_focus_moves_to_the_form_heading(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        expect(booking_page.get_by_role("heading", name=heading_for(day))).to_be_focused()

    def test_back_button_returns_to_the_calendar_without_a_date(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        expect(booking_page.get_by_role("heading", name=heading_for(day))).to_be_visible()
        booking_page.go_back()
        expect(booking_page).not_to_have_url(re.compile("date="))
        expect(booking_page.get_by_role("heading", name=re.compile("^Request"))).to_have_count(0)

    def test_request_can_be_sent_from_the_form_that_slid_in(self, booking_page: Page, day):
        date_link(booking_page, day).click()
        booking_page.get_by_label("Your name").fill("Avery Jones")
        booking_page.get_by_label("Email").fill("avery@example.com")
        booking_page.get_by_label("Event type").select_option("wedding")
        booking_page.get_by_label("Number of guests").fill("120")
        booking_page.get_by_role("button", name="Send Request").click()
        expect(booking_page.get_by_role("heading", name="Thank You")).to_be_visible()
        assert Booking.objects.get().event_date == day


def test_date_links_still_work_without_javascript(browser, base_url, day):
    context = browser.new_context(java_script_enabled=False, base_url=base_url)
    page = context.new_page()
    page.goto(f"/book/?month={day:%Y-%m}")
    date_link(page, day).click()
    expect(page.get_by_role("heading", name=heading_for(day))).to_be_visible()
    assert page.url.endswith("#request")
    context.close()
