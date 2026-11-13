"""Installment generation (D2, D8, D11, D17). Pure: the group comes from outside."""

from __future__ import annotations

import calendar
import datetime as dt

from kotsu.domain.line import ParsedLine
from kotsu.domain.models import Installment, NewEntry
from kotsu.domain.month import Month


def installment_date(first: dt.date, index: int) -> dt.date:
    """Date of installment `index` (0 = first): same day, `index` months later.

    A day the month lacks becomes the last day of the month (31/01 -> 28/02).
    """
    month = Month.of(first).add(index)
    last = calendar.monthrange(month.year, month.month)[1]
    return dt.date(month.year, month.month, min(first.day, last))


def generate(
    line: ParsedLine,
    account_id: int,
    category_id: int | None,
    group: str | None,
) -> list[NewEntry]:
    """Turns the line into entries: one, or one per installment in consecutive months.

    The typed amount is that of each installment (D11). `group` is required with installments.
    """
    if line.installments == 1:
        return [
            NewEntry(line.date, line.description, line.amount, line.kind, account_id, category_id)
        ]
    if not group:
        raise ValueError("installments need a group")
    return [
        NewEntry(
            installment_date(line.date, i),
            line.description,
            line.amount,
            line.kind,
            account_id,
            category_id,
            Installment(group, i + 1, line.installments),
        )
        for i in range(line.installments)
    ]
