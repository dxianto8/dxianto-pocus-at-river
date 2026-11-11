"""
Month grids for the booking calendars. Plain Python with no database access, so the
rules for which days can be booked are easy to test on their own.
"""

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from django.conf import settings

# US calendars start the week on Sunday.
_weeks = calendar.Calendar(firstweekday=calendar.SUNDAY)


class DayState(StrEnum):
    AVAILABLE = "available"
    ON_HOLD = "on_hold"  # a request is waiting for the venue to confirm it
    BOOKED = "booked"  # confirmed, or blocked by the venue
    UNAVAILABLE = "unavailable"  # in the past, or too far ahead to book

    @property
    def label(self) -> str:
        return {
            DayState.AVAILABLE: "Available",
            DayState.ON_HOLD: "On hold",
            DayState.BOOKED: "Booked",
            DayState.UNAVAILABLE: "Not bookable",
        }[self]


@dataclass(frozen=True)
class Day:
    date: date
    in_month: bool
    state: DayState
    is_today: bool


@dataclass(frozen=True)
class Month:
    first: date
    weeks: list[list[Day]]
    previous: date | None  # first day of the previous month, if it can be shown
    next: date | None  # first day of the next month, if it can be shown

    @property
    def label(self) -> str:
        return self.first.strftime("%B %Y")


def add_months(day: date, months: int) -> date:
    """Same day of the month, `months` later (or earlier), clamped to the month's last day."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def month_dates(first: date) -> list[list[date]]:
    """Every date shown in a month view: full Sunday-to-Saturday weeks."""
    return _weeks.monthdatescalendar(first.year, first.month)


def bookable_range(today: date, months_ahead: int | None = None) -> tuple[date, date]:
    """First and last dates that can be requested: today up to `months_ahead` months from now."""
    if months_ahead is None:
        months_ahead = settings.BOOKING_MAX_MONTHS_AHEAD
    return today, add_months(today, months_ahead)


def parse_month(value: str | None, *, today: date, months_ahead: int | None = None) -> date:
    """Turn "YYYY-MM" into the first day of that month, kept within the bookable range."""
    first_allowed, last_allowed = (d.replace(day=1) for d in bookable_range(today, months_ahead))
    try:
        year, month = (int(part) for part in (value or "").split("-"))
        chosen = date(year, month, 1)
    except ValueError:
        return first_allowed
    return min(max(chosen, first_allowed), last_allowed)


def build_month(
    first: date,
    *,
    today: date,
    taken: Mapping[date, DayState],
    months_ahead: int | None = None,
) -> Month:
    """A month as full Sunday-to-Saturday weeks, with each day's booking state."""
    start, end = bookable_range(today, months_ahead)

    def state_of(day: date) -> DayState:
        if not start <= day <= end:
            return DayState.UNAVAILABLE
        return taken.get(day, DayState.AVAILABLE)

    weeks = [
        [Day(d, d.month == first.month, state_of(d), d == today) for d in week]
        for week in month_dates(first)
    ]
    previous = add_months(first, -1)
    following = add_months(first, 1)
    return Month(
        first=first,
        weeks=weeks,
        previous=previous if previous >= start.replace(day=1) else None,
        next=following if following <= end.replace(day=1) else None,
    )
