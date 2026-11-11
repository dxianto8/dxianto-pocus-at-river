from datetime import date

from bookings.calendar import DayState, add_months, build_month, parse_month

TODAY = date(2026, 11, 11)  # a Wednesday


class TestAddMonths:
    def test_keeps_the_day_when_it_exists(self):
        assert add_months(TODAY, 24) == date(2028, 11, 11)

    def test_clamps_to_the_end_of_shorter_months(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert add_months(date(2027, 12, 31), 2) == date(2028, 2, 29)

    def test_goes_backwards(self):
        assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)


class TestBuildMonth:
    def test_weeks_run_sunday_to_saturday(self):
        month = build_month(date(2026, 11, 1), today=TODAY, taken={})
        assert all(len(week) == 7 for week in month.weeks)
        assert all(week[0].date.weekday() == 6 for week in month.weeks)  # Sunday
        assert month.weeks[0][0].date == date(2026, 11, 1)  # Nov 1 2026 is a Sunday
        assert month.label == "November 2026"

    def test_marks_days_from_neighbouring_months(self):
        month = build_month(date(2026, 12, 1), today=TODAY, taken={})
        first_week = month.weeks[0]
        assert [d.in_month for d in first_week[:3]] == [False, False, True]  # Dec 1 is a Tuesday

    def test_past_days_are_unavailable_and_today_is_bookable(self):
        month = build_month(date(2026, 11, 1), today=TODAY, taken={})
        days = {d.date: d for week in month.weeks for d in week}
        assert days[date(2026, 11, 10)].state is DayState.UNAVAILABLE
        assert days[TODAY].state is DayState.AVAILABLE
        assert days[TODAY].is_today

    def test_taken_days_use_their_state(self):
        taken = {date(2026, 12, 5): DayState.ON_HOLD, date(2026, 12, 12): DayState.BOOKED}
        month = build_month(date(2026, 12, 1), today=TODAY, taken=taken)
        days = {d.date: d for week in month.weeks for d in week}
        assert days[date(2026, 12, 5)].state is DayState.ON_HOLD
        assert days[date(2026, 12, 12)].state is DayState.BOOKED
        assert days[date(2026, 12, 19)].state is DayState.AVAILABLE

    def test_days_beyond_24_months_are_unavailable(self):
        month = build_month(date(2028, 11, 1), today=TODAY, taken={})
        days = {d.date: d for week in month.weeks for d in week}
        assert days[date(2028, 11, 11)].state is DayState.AVAILABLE
        assert days[date(2028, 11, 12)].state is DayState.UNAVAILABLE

    def test_no_previous_link_from_the_current_month(self):
        month = build_month(date(2026, 11, 1), today=TODAY, taken={})
        assert month.previous is None
        assert month.next == date(2026, 12, 1)

    def test_no_next_link_from_the_last_bookable_month(self):
        month = build_month(date(2028, 11, 1), today=TODAY, taken={})
        assert month.previous == date(2028, 10, 1)
        assert month.next is None


class TestParseMonth:
    def test_reads_year_and_month(self):
        assert parse_month("2027-03", today=TODAY) == date(2027, 3, 1)

    def test_falls_back_to_the_current_month(self):
        assert parse_month(None, today=TODAY) == date(2026, 11, 1)
        assert parse_month("not-a-month", today=TODAY) == date(2026, 11, 1)
        assert parse_month("2027-13", today=TODAY) == date(2026, 11, 1)

    def test_clamps_to_the_bookable_range(self):
        assert parse_month("2020-01", today=TODAY) == date(2026, 11, 1)
        assert parse_month("2031-01", today=TODAY) == date(2028, 11, 1)
