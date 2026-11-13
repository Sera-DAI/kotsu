"""Quick-line parser and installment generation (M1 criteria 1 to 7)."""

import datetime as dt

import pytest

from kotsu.domain import installments
from kotsu.domain.line import LineError, ParsedLine, parse
from kotsu.domain.models import Kind

TODAY = dt.date(2026, 11, 8)


def test_example_expense_with_category_and_account():
    line = parse("89,90 groceries #food @nubank", TODAY)
    assert line == ParsedLine(
        amount=8990,
        kind=Kind.EXPENSE,
        description="groceries",
        date=TODAY,
        category="food",
        account="nubank",
    )


def test_example_income():
    line = parse("+3500 salary @itaú", TODAY)
    assert (line.kind, line.amount, line.description, line.account) == (
        Kind.INCOME,
        350000,
        "salary",
        "itaú",
    )
    assert line.category is None


def test_example_installments_amount_is_per_installment():
    line = parse("120 fridge #home @nubank 10x", TODAY)
    assert (line.amount, line.installments, line.total) == (12000, 10, 120000)


def test_free_order_after_the_amount():
    a = parse("120 @nubank 3x fridge #home new", TODAY)
    assert (a.description, a.account, a.category, a.installments) == (
        "fridge new",
        "nubank",
        "home",
        3,
    )


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("89,90", 8990),
        ("89.90", 8990),
        ("89,9", 8990),
        ("89", 8900),
        ("0,05", 5),
        ("1.234,56", 123456),
        ("1.234", 123400),
        ("1234,56", 123456),
        ("-89,90", 8990),
        ("+1.000.000", 100000000),
    ],
)
def test_amount_formats(text, cents):
    assert parse(f"{text} x", TODAY).amount == cents


def test_explicit_minus_is_expense():
    assert parse("-89,90 x", TODAY).kind is Kind.EXPENSE


@pytest.mark.parametrize(
    "text",
    ["", "   ", "groceries 89,90", "0", "0,00", "89,901", "1.23.4", "12a", "+", "-", "1,2,3"],
)
def test_invalid_amount_becomes_an_error(text):
    with pytest.raises(LineError):
        parse(text, TODAY)


@pytest.mark.parametrize(
    ("text", "date"),
    [
        ("10 x", TODAY),
        ("10 x today", TODAY),
        ("10 x yesterday", dt.date(2026, 11, 7)),
        ("10 x Yesterday", dt.date(2026, 11, 7)),
        ("10 x hoje", TODAY),
        ("10 x Ontem", dt.date(2026, 11, 7)),
        ("10 x 15/10", dt.date(2026, 10, 15)),
        ("10 x 5/1", dt.date(2026, 1, 5)),
        ("10 x 15/10/2025", dt.date(2025, 10, 15)),
        ("10 x 15/10/25", dt.date(2025, 10, 15)),
    ],
)
def test_dates(text, date):
    assert parse(text, TODAY).date == date


def test_yesterday_on_the_first_goes_back_a_month():
    assert parse("10 yesterday", dt.date(2026, 3, 1)).date == dt.date(2026, 2, 28)


@pytest.mark.parametrize(
    ("text", "excerpt"),
    [
        ("10 x 31/02", "impossible date"),
        ("10 x 15/13", "impossible date"),
        ("10 #a #b", "only one #category"),
        ("10 @a @b", "only one @account"),
        ("10 x 2x 3x", "only one installment count"),
        ("10 x yesterday 15/10", "only one date"),
        ("10 x 1x", "2x to 120x"),
        ("10 x 121x", "2x to 120x"),
        ("10 x #", "missing the category name"),
        ("10 x @", "missing the account name"),
    ],
)
def test_errors_have_a_message(text, excerpt):
    with pytest.raises(LineError, match=excerpt):
        parse(text, TODAY)


def test_description_may_be_empty():
    assert parse("+3500 @itaú", TODAY).description == ""


def test_installments_in_consecutive_months_same_group():
    line = parse("120 fridge #home @nubank 10x", TODAY)
    new = installments.generate(line, account_id=1, category_id=2, group="g")
    assert len(new) == 10
    assert [n.date for n in new][:3] == [
        dt.date(2026, 11, 8),
        dt.date(2026, 12, 8),
        dt.date(2027, 1, 8),
    ]
    assert new[-1].date == dt.date(2027, 8, 8)
    assert {n.amount for n in new} == {12000}
    assert {n.installment.group for n in new} == {"g"}
    assert [n.installment.label for n in new] == [f"{i}/10" for i in range(1, 11)]
    assert all(n.account_id == 1 and n.category_id == 2 for n in new)


def test_day_the_month_lacks_becomes_the_last_day():
    assert installments.installment_date(dt.date(2027, 1, 31), 1) == dt.date(2027, 2, 28)
    assert installments.installment_date(dt.date(2028, 1, 31), 1) == dt.date(2028, 2, 29)
    assert installments.installment_date(dt.date(2027, 1, 31), 2) == dt.date(2027, 3, 31)


def test_single_entry_has_no_installment():
    (new,) = installments.generate(parse("10 x", TODAY), 1, None, None)
    assert new.installment is None


def test_installments_without_group_is_a_programming_error():
    with pytest.raises(ValueError):
        installments.generate(parse("10 x 3x", TODAY), 1, None, None)
