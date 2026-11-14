"""Quick-line parser (D10, D11). Pure: takes text and today's date.

Syntax: the amount comes first; the rest is free-form.

    89,90 groceries #food @nubank          expense (no sign or with -)
    +3500 salary @itau                     income
    120 fridge #home @nubank 10x           10 installments of 120,00, one per month
    ... yesterday | 15/10 | 15/10/2025     date (default: today)
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from kotsu.domain import currency
from kotsu.domain.models import Kind

MAX_INSTALLMENTS = 120

# Words for today and yesterday. The Portuguese ones still work for existing habits.
_TODAY = ("today", "hoje")
_YESTERDAY = ("yesterday", "ontem")

_INSTALLMENTS = re.compile(r"(\d+)[xX]")
_DATE = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?")
_AMOUNT = re.compile(r"([+-]?)(.+)")
_DIGITS = re.compile(r"\d+")
_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")


class LineError(ValueError):
    """A line that cannot be saved. The message is shown to the user as is."""


@dataclass(frozen=True, slots=True)
class ParsedLine:
    """What the line says, before account and category names are resolved into ids."""

    amount: int  # cents, positive; per installment when there are installments (D11)
    kind: Kind
    description: str
    date: dt.date
    category: str | None = None
    account: str | None = None
    installments: int = 1
    has_date: bool = False  # the date was written in the line (otherwise it is today)

    @property
    def total(self) -> int:
        return self.amount * self.installments


def parse(line: str, today: dt.date) -> ParsedLine:
    """Reads a quick line. Raises `LineError` with a message for the user."""
    parts = line.split()
    if not parts:
        raise LineError("type the amount first, e.g. 89,90 groceries @nubank")

    kind, amount = _read_amount(parts[0])
    description: list[str] = []
    category = account = None
    date: dt.date | None = None
    installments: int | None = None

    for part in parts[1:]:
        if part.startswith("#"):
            if category is not None:
                raise LineError("only one #category per entry")
            category = _name(part, "category")
        elif part.startswith("@"):
            if account is not None:
                raise LineError("only one @account per entry")
            account = _name(part, "account")
        elif m := _INSTALLMENTS.fullmatch(part):
            if installments is not None:
                raise LineError("only one installment count (e.g. 10x)")
            installments = int(m.group(1))
            if not 2 <= installments <= MAX_INSTALLMENTS:
                raise LineError(f"installments go from 2x to {MAX_INSTALLMENTS}x")
        elif (d := _read_date(part, today)) is not None:
            if date is not None:
                raise LineError("only one date per entry")
            date = d
        else:
            description.append(part)

    return ParsedLine(
        amount=amount,
        kind=kind,
        description=" ".join(description),
        date=date or today,
        category=category,
        account=account,
        installments=installments or 1,
        has_date=date is not None,
    )


def _name(part: str, what: str) -> str:
    name = part[1:]
    if not name:
        raise LineError(f"missing the {what} name after {part[0]}")
    return name


def _read_amount(text: str) -> tuple[Kind, int]:
    m = _AMOUNT.fullmatch(text)
    if not m:
        raise LineError(f"unreadable amount: {text} (use 89,90 or 1.234,56)")
    sign, number = m.groups()
    kind = Kind.INCOME if sign == "+" else Kind.EXPENSE
    cents = _cents(number)
    if cents is None:
        raise LineError(f"unreadable amount: {text} (use 89,90 or 1.234,56)")
    if cents == 0:
        raise LineError("the amount must be greater than zero")
    return kind, cents


def _cents(number: str) -> int | None:
    """'89,90' '89.90' '89' '1.234,56' '1234,5' -> cents. Unreadable -> None.

    A comma is always the decimal separator and a dot the thousands separator. Without a
    comma, a dot followed by 1 or 2 digits at the end is decimal (89.90); in groups of 3 it
    separates thousands (1.234).
    """
    if "," in number:
        whole, _, fraction = number.partition(",")
    elif re.fullmatch(r"\d+\.\d{1,2}", number):
        whole, _, fraction = number.partition(".")
    else:
        whole, fraction = number, ""
    if "." in whole:
        if not _THOUSANDS.fullmatch(whole):
            return None
        whole = whole.replace(".", "")
    if not _DIGITS.fullmatch(whole) or (fraction and not _DIGITS.fullmatch(fraction)):
        return None
    if len(fraction) > 2:
        return None
    return int(whole) * 100 + int(fraction.ljust(2, "0") or 0)


def _read_date(text: str, today: dt.date) -> dt.date | None:
    """'today', 'yesterday', 'dd/mm', 'dd/mm/yy', 'dd/mm/yyyy'. Not a date -> None."""
    lower = text.casefold()
    if lower in _TODAY:
        return today
    if lower in _YESTERDAY:
        return today - dt.timedelta(days=1)
    m = _DATE.fullmatch(text)
    if not m:
        return None
    day, month, year = m.groups()
    year_num = today.year if year is None else int(year) + (2000 if len(year) == 2 else 0)
    try:
        return dt.date(year_num, int(month), int(day))
    except ValueError:
        raise LineError(f"impossible date: {text}") from None


def build(
    amount: int,
    kind: Kind,
    description: str,
    account: str,
    category: str | None = None,
    date: dt.date | None = None,
) -> str:
    """The reverse of `parse`: the line that copy and edit show (D27, D28).

    Without `date`, the line carries no date (it becomes today when saved). Never carries
    installments.
    """
    parts = [("+" if kind is Kind.INCOME else "") + currency.format_cents(amount)]
    if description:
        parts.append(description)
    if category:
        parts.append(f"#{category}")
    parts.append(f"@{account}")
    if date is not None:
        parts.append(date.strftime("%d/%m/%Y"))
    return " ".join(parts)
