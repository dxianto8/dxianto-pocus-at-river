"""The booking calendar: today stands out, and the "Your date" card keeps even margins."""

from datetime import timedelta

import pytest
from django.utils import timezone
from playwright.sync_api import Page, expect

TODAY_ORANGE = "rgb(184, 86, 26)"


def test_today_is_on_an_orange_tile(page: Page):
    today = timezone.localdate()
    page.goto(f"/book/?month={today:%Y-%m}")
    number = page.locator(f'td[data-date="{today:%Y-%m-%d}"] .day__number')
    expect(number).to_have_css("background-color", TODAY_ORANGE)
    expect(number).to_have_css("color", "rgb(255, 255, 255)")
    other = page.locator(f'td[data-date="{today + timedelta(days=1):%Y-%m-%d}"] .day__number')
    if other.count():
        expect(other).not_to_have_css("background-color", TODAY_ORANGE)


@pytest.mark.parametrize("width", [1440, 1024])
def test_your_date_card_has_even_margins(page: Page, width):
    # A Wednesday, whose long name used to push the card's contents past its right edge.
    day = timezone.localdate() + timedelta(days=14)
    day += timedelta(days=(2 - day.weekday()) % 7)
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"/book/?month={day:%Y-%m}&date={day:%Y-%m-%d}&session=full")
    margins = page.evaluate(
        """() => {
          const card = document.querySelector('.calendar__aside').getBoundingClientRect();
          return [...document.querySelectorAll('.calendar__aside .pick > *, .calendar__legend')]
            .map(el => {
              const r = el.getBoundingClientRect();
              return [Math.round(r.left - card.left), Math.round(card.right - r.right)];
            });
        }"""
    )
    assert margins
    for left, right in margins:
        assert abs(left - right) <= 1, margins
