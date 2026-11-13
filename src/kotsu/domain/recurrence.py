"""Dates of recurring entries (D36). Pure: no database."""

from __future__ import annotations

import calendar
import datetime as dt

from kotsu.domain.month import Month


def date_in_month(day: int, month: Month) -> dt.date:
    """`day` in the month; a day the month lacks becomes the last day (31 -> 28/02)."""
    last = calendar.monthrange(month.year, month.month)[1]
    return dt.date(month.year, month.month, min(day, last))


def months_to_generate(generated_until: Month, until: Month) -> list[Month]:
    """Months after `generated_until` up to `until`, inclusive. Empty if already generated."""
    count = (until.year * 12 + until.month) - (generated_until.year * 12 + generated_until.month)
    return [generated_until.add(i) for i in range(1, count + 1)]
