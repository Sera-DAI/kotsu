import datetime as dt

import pytest

from kotsu.domain import currency
from kotsu.domain.models import Entry, Installment, Kind, NewEntry
from kotsu.domain.month import Month
from kotsu.domain.totals import MonthTotals


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "0,00"),
        (5, "0,05"),
        (8990, "89,90"),
        (123456, "1.234,56"),
        (100000000, "1.000.000,00"),
        (-8990, "89,90"),
    ],
)
def test_format_without_sign(cents, text):
    assert currency.format_cents(cents) == text


def test_month_rolls_over_the_year():
    assert Month(2026, 12).next() == Month(2027, 1)
    assert Month(2026, 1).previous() == Month(2025, 12)
    assert Month(2026, 11).add(10) == Month(2027, 9)
    assert Month(2026, 11).add(-23) == Month(2024, 12)


def test_month_bounds_and_name():
    m = Month.of(dt.date(2026, 2, 17))
    assert (m.start, m.end_exclusive) == (dt.date(2026, 2, 1), dt.date(2026, 3, 1))
    assert m.name == "February 2026"
    with pytest.raises(ValueError):
        Month(2026, 13)


def test_balance_is_income_minus_expenses():
    assert MonthTotals(350000, 412000).balance == -62000


def test_amount_must_be_positive_cents():
    today = dt.date(2026, 11, 8)
    with pytest.raises(TypeError):
        NewEntry(today, "x", 89.9, Kind.EXPENSE, 1)
    with pytest.raises(ValueError):
        NewEntry(today, "x", -8990, Kind.EXPENSE, 1)
    with pytest.raises(ValueError):
        NewEntry(today, "x", 0, Kind.EXPENSE, 1)


def test_every_entry_has_an_account():
    today = dt.date(2026, 11, 8)
    assert NewEntry(today, "x", 100, Kind.EXPENSE, 1).category_id is None
    with pytest.raises(TypeError):
        NewEntry(today, "x", 100, Kind.EXPENSE)  # the account is required
    with pytest.raises(ValueError, match="account"):
        NewEntry(today, "x", 100, Kind.EXPENSE, None)


def test_installment():
    assert Installment("g", 3, 10).label == "3/10"
    with pytest.raises(ValueError):
        Installment("g", 11, 10)


def test_sign_comes_from_the_kind():
    base = dict(
        id=1,
        date=dt.date(2026, 11, 8),
        description="x",
        amount=100,
        account_id=1,
        category_id=None,
        installment=None,
    )
    assert Entry(kind=Kind.INCOME, **base).signed_amount == 100
    assert Entry(kind=Kind.EXPENSE, **base).signed_amount == -100
