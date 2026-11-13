"""Saving the quick line, installments and "only this one or all?" (criteria 3, 4 and 10)."""

import datetime as dt
import sqlite3

import pytest

from kotsu.domain import installments
from kotsu.domain.line import parse
from kotsu.domain.models import Installment, Kind, NewEntry, Scope
from kotsu.domain.month import Month

TODAY = dt.date(2026, 11, 8)


def _save(db, text, account_id, category_id=None):
    line = parse(text, TODAY)
    group = db.new_installment_group() if line.installments > 1 else None
    return db.insert_entries(installments.generate(line, account_id, category_id, group))


def test_ten_installments_one_per_month(db):
    nubank = db.create_account("nubank", "#8a2be2")
    _save(db, "120 10x", nubank.id)
    for i in range(10):
        month = Month(2026, 11).add(i)
        (item,) = db.month_entries(month)
        assert (item.amount, item.kind, item.installment.label) == (
            12000,
            Kind.EXPENSE,
            f"{i + 1}/10",
        )
        assert db.month_totals(month).expenses == 12000
    assert db.month_entries(Month(2027, 9)) == []


def test_installments_go_in_all_or_none(db):
    nubank = db.create_account("nubank", "#8a2be2")
    line = parse("120 fridge 3x", TODAY)
    new = installments.generate(line, nubank.id, None, "g")
    new[-1] = NewEntry(TODAY, "x", 1, Kind.EXPENSE, 999)  # account does not exist
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_entries(new)
    assert db.month_entries(Month(2026, 11)) == []


def test_lookup_by_name_ignores_case_including_accented(db):
    itau = db.create_account("Itaú", "#ff7a00")
    home = db.create_category("Home")
    assert db.account_by_name("ITAÚ") == itau
    assert db.account_by_name("nubank") is None
    assert db.category_by_name(" home ") == home


@pytest.fixture
def purchase(db):
    nubank = db.create_account("nubank", "#8a2be2")
    ids = _save(db, "120 fridge 3x", nubank.id)
    single = _save(db, "10 coffee", nubank.id)[0]
    return ids, single


def test_deleting_an_installment_deletes_all_by_default(db, purchase):
    ids, single = purchase
    assert db.delete(ids[1]) == 3
    assert all(db.entry(i) is None for i in ids)
    assert db.entry(single) is not None


def test_delete_only_this(db, purchase):
    ids, _ = purchase
    assert db.delete(ids[1], Scope.ONLY_THIS) == 1
    assert db.entry(ids[0]) and db.entry(ids[2])


def test_rename_all_or_only_this(db, purchase):
    ids, single = purchase
    assert db.rename(ids[0], "brastemp fridge") == 3
    assert {db.entry(i).description for i in ids} == {"brastemp fridge"}
    assert db.rename(ids[2], "last", Scope.ONLY_THIS) == 1
    assert db.entry(ids[2]).description == "last"
    assert db.entry(ids[1]).description == "brastemp fridge"
    assert db.entry(single).description == "coffee"


def test_single_entry_ignores_scope(db, purchase):
    _, single = purchase
    assert db.delete(single, Scope.ALL) == 1


def test_installment_read_from_the_database(db):
    nubank = db.create_account("nubank", "#8a2be2")
    (i,) = db.insert_entries(
        [NewEntry(TODAY, "x", 1, Kind.EXPENSE, nubank.id, installment=Installment("g", 2, 5))]
    )
    assert db.entry(i).installment == Installment("g", 2, 5)
