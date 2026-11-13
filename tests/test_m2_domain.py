"""M2 without the UI: filter, building the line and database queries (criterion 13)."""

import datetime as dt

import pytest

from kotsu.domain.filter import Filter, TypedFilter, parse_filter
from kotsu.domain.line import LineError, build, parse
from kotsu.domain.models import Installment, Kind, NewEntry, Scope
from kotsu.domain.month import Month
from kotsu.domain.totals import MonthTotals

TODAY = dt.date(2026, 11, 8)
NOV = Month(2026, 11)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("@nubank", TypedFilter(account="nubank")),
        ("#home", TypedFilter(category="home")),
        ("@nubank #home", TypedFilter(account="nubank", category="home")),
        ("  nubank ", TypedFilter(either="nubank")),
        ("", TypedFilter()),
    ],
)
def test_parse_filter(text, expected):
    assert parse_filter(text) == expected


@pytest.mark.parametrize("text", ["@a @b", "#a #b", "@", "#", "@nubank home"])
def test_invalid_filter(text):
    with pytest.raises(LineError):
        parse_filter(text)


def test_empty_filter_is_not_active():
    assert parse_filter("").empty
    assert not Filter().active and Filter(account_id=1).active


@pytest.mark.parametrize(
    ("args", "text"),
    [
        (
            (8990, Kind.EXPENSE, "groceries", "nubank", "food", None),
            "89,90 groceries #food @nubank",
        ),
        (
            (350000, Kind.INCOME, "salary", "itaú", None, dt.date(2025, 10, 3)),
            "+3.500,00 salary @itaú 03/10/2025",
        ),
        ((123456, Kind.EXPENSE, "", "nubank", None, None), "1.234,56 @nubank"),
    ],
)
def test_build_and_parse_back(args, text):
    amount, kind, description, account, category, date = args
    line = build(amount, kind, description, account, category, date)
    assert line == text
    back = parse(line, TODAY)
    assert (back.amount, back.kind, back.description) == (amount, kind, description)
    assert (back.account, back.category, back.installments) == (account, category, 1)
    assert back.date == (date or TODAY) and back.has_date == (date is not None)


def _base(db):
    nubank = db.create_account("nubank", "#8a2be2")
    itau = db.create_account("itaú", "#ff7a00")
    db.create_account("idle", "#1f8fff")
    home = db.create_category("home")
    db.insert_entries(
        [
            NewEntry(dt.date(2026, 11, 5), "salary", 350000, Kind.INCOME, itau.id),
            NewEntry(dt.date(2026, 11, 6), "power", 20000, Kind.EXPENSE, itau.id, home.id),
            NewEntry(dt.date(2026, 11, 7), "groceries", 8990, Kind.EXPENSE, nubank.id),
            NewEntry(dt.date(2026, 11, 8), "sofa", 50000, Kind.EXPENSE, nubank.id, home.id),
            NewEntry(dt.date(2026, 10, 8), "october", 100, Kind.EXPENSE, nubank.id),
        ]
    )
    return nubank, itau, home


def test_totals_by_account_add_up_to_the_top(db):
    nubank, itau, _ = _base(db)
    by_account = db.totals_by_account(NOV)
    assert by_account == {
        nubank.id: MonthTotals(0, 58990, 2),
        itau.id: MonthTotals(350000, 20000, 2),
    }  # "idle" had no entry: it does not show up (D29)
    top = db.month_totals(NOV)
    assert sum(t.income for t in by_account.values()) == top.income
    assert sum(t.expenses for t in by_account.values()) == top.expenses


def test_filter_applies_to_totals_and_list(db):
    nubank, itau, home = _base(db)
    only_home = Filter(category_id=home.id)
    assert db.month_totals(NOV, only_home) == MonthTotals(0, 70000, 2)
    assert [x.description for x in db.month_entries(NOV, filter=only_home)] == ["sofa", "power"]
    assert db.totals_by_account(NOV, only_home).keys() == {nubank.id, itau.id}
    both = Filter(account_id=nubank.id, category_id=home.id)
    assert [x.description for x in db.month_entries(NOV, filter=both)] == ["sofa"]


def test_editing_a_single_entry_changes_everything_including_date(db):
    nubank, itau, home = _base(db)
    groceries = next(x for x in db.month_entries(NOV) if x.description == "groceries")
    new = NewEntry(dt.date(2026, 12, 1), "market", 4500, Kind.INCOME, itau.id, home.id)
    assert db.edit(groceries.id, new) == 1
    edited = db.entry(groceries.id)
    assert (edited.date, edited.description, edited.amount) == (
        dt.date(2026, 12, 1),
        "market",
        4500,
    )
    assert (edited.kind, edited.account_id, edited.category_id) == (
        Kind.INCOME,
        itau.id,
        home.id,
    )


def test_editing_all_installments_keeps_dates_and_only_this_changes_one(db):
    nubank, itau, home = _base(db)
    group = db.new_installment_group()
    ids = db.insert_entries(
        [
            NewEntry(
                dt.date(2026, 11 + i, 2),
                "tv",
                10000,
                Kind.EXPENSE,
                nubank.id,
                installment=Installment(group, i + 1, 2),
            )
            for i in range(2)
        ]
    )
    new = NewEntry(TODAY, "television", 12000, Kind.EXPENSE, itau.id, home.id)
    assert db.edit(ids[0], new, Scope.ALL) == 2
    all_ = [db.entry(i) for i in ids]
    assert [x.date for x in all_] == [dt.date(2026, 11, 2), dt.date(2026, 12, 2)]
    assert {(x.description, x.amount, x.account_id, x.installment.total) for x in all_} == {
        ("television", 12000, itau.id, 2)
    }
    only = NewEntry(dt.date(2026, 12, 20), "tv", 9000, Kind.EXPENSE, itau.id)
    assert db.edit(ids[1], only, Scope.ONLY_THIS) == 1
    assert db.entry(ids[1]).date == dt.date(2026, 12, 20)
    assert db.entry(ids[0]).amount == 12000
