"""Calendar helpers for billing cycles and delivery estimates."""

import calendar
import datetime as dt


def add_months(day: dt.date, months: int) -> dt.date:
    """Same day-of-month `months` later (or earlier, if negative). When the target
    month is shorter, clamp to its last day: Jan 31 + 1 -> Feb 28 (29 in leap
    years), Mar 31 + 1 -> Apr 30, Aug 15 + 1 -> Sep 15."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def business_days_between(start: dt.date, end: dt.date, holidays=()) -> int:
    """Number of weekdays in the half-open range [start, end) that are not
    holidays. Returns 0 when end <= start."""
    if end <= start:
        return 0
    holidays = set(holidays)
    count, current = 0, start
    while current < end:
        if current.weekday() < 5 and current not in holidays:
            count += 1
        current += dt.timedelta(days=1)
    return count


def add_business_days(start: dt.date, days: int, holidays=()) -> dt.date:
    """The date `days` weekdays after `start`, skipping holidays. `start` itself
    is not counted. days == 0 returns start."""
    holidays = set(holidays)
    current = start
    while days > 0:
        current += dt.timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            days -= 1
    return current
