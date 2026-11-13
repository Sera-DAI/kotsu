"""Recurring categories (D36): repeat every month, endlessly, until the person ends them."""

import datetime as dt
import sqlite3

from textual.widgets import DataTable, Input, Static

from kotsu.domain.models import Kind, NewEntry, Scope
from kotsu.domain.month import Month
from kotsu.domain.recurrence import date_in_month, months_to_generate
from kotsu.storage.database import Database
from kotsu.ui.app import MONTHS_AHEAD, KotsuApp
from kotsu.ui.dialogs import OnlyThisOrUpcoming, YesOrNo

TODAY = dt.date(2026, 11, 8)


def _series(db, day=dt.date(2026, 11, 4)):
    account = db.create_account("itaú", "#ff7a00")
    cat = db.create_category("rent", recurring=True)
    (id_,) = db.insert_entries(
        [NewEntry(day, "rent", 150000, Kind.EXPENSE, account.id, cat.id, recurrence_group="g1")]
    )
    return id_


def test_domain_dates():
    assert date_in_month(31, Month(2027, 2)) == dt.date(2027, 2, 28)
    assert date_in_month(5, Month(2027, 2)) == dt.date(2027, 2, 5)
    assert months_to_generate(Month(2026, 11), Month(2027, 1)) == [Month(2026, 12), Month(2027, 1)]
    assert months_to_generate(Month(2026, 11), Month(2026, 11)) == []
    assert months_to_generate(Month(2026, 11), Month(2026, 8)) == []


def test_extend_generates_up_to_the_month_and_does_not_duplicate(db):
    _series(db)
    assert db.extend_recurrences(Month(2027, 2)) == 3
    assert db.extend_recurrences(Month(2027, 2)) == 0
    assert db.extend_recurrences(Month(2026, 12)) == 0  # only moves forward
    for month in (Month(2026, 11), Month(2026, 12), Month(2027, 1), Month(2027, 2)):
        (item,) = db.month_entries(month)
        assert item.amount == 150000 and item.date.day == 4


def test_day_31_becomes_the_last_day(db):
    _series(db, dt.date(2026, 10, 31))
    db.extend_recurrences(Month(2026, 12))
    months = (Month(2026, 11), Month(2026, 12))
    dates = {i.date for m in months for i in db.month_entries(m)}
    assert dates == {dt.date(2026, 11, 30), dt.date(2026, 12, 31)}


def test_only_this_month_does_not_come_back(db):
    id_ = _series(db)
    db.extend_recurrences(Month(2027, 1))
    (dec,) = db.month_entries(Month(2026, 12))
    db.delete(dec.id, Scope.ONLY_THIS)
    db.extend_recurrences(Month(2027, 3))
    assert db.month_entries(Month(2026, 12)) == []
    assert len(db.month_entries(Month(2027, 3))) == 1
    assert db.entry(id_) is not None


def test_upcoming_ends_and_keeps_the_past(db):
    _series(db)
    db.extend_recurrences(Month(2027, 2))
    (jan,) = db.month_entries(Month(2027, 1))
    assert db.delete(jan.id, Scope.UPCOMING) == 2  # jan and feb
    db.extend_recurrences(Month(2027, 6))
    assert len(db.month_entries(Month(2026, 12))) == 1
    assert db.month_entries(Month(2027, 1)) == []
    assert db.month_entries(Month(2027, 6)) == []


def test_editing_upcoming_changes_template_and_future_months(db):
    _series(db)
    db.extend_recurrences(Month(2027, 1))
    (dec,) = db.month_entries(Month(2026, 12))
    account = db.list_accounts()[0]
    new = NewEntry(dec.date, "new rent", 160000, Kind.EXPENSE, account.id, dec.category_id)
    assert db.edit(dec.id, new, Scope.UPCOMING) == 2  # dec and jan
    db.extend_recurrences(Month(2027, 3))
    assert db.month_entries(Month(2026, 11))[0].amount == 150000
    for month in (Month(2026, 12), Month(2027, 3)):
        (item,) = db.month_entries(month)
        assert (item.amount, item.description) == (160000, "new rent")


def test_make_recurring_and_refusals(db):
    account = db.create_account("itaú", "#ff7a00")
    (id_,) = db.insert_entries(
        [NewEntry(dt.date(2026, 11, 5), "internet", 9990, Kind.EXPENSE, account.id)]
    )
    assert db.make_recurring(id_) is True
    assert db.make_recurring(id_) is False
    db.extend_recurrences(Month(2026, 12))
    assert len(db.month_entries(Month(2026, 12))) == 1


def test_migration_0002_keeps_data(tmp_path):
    from kotsu.storage import migrations
    from kotsu.storage.database import migrate

    path = tmp_path / "money.sqlite"
    connection = sqlite3.connect(path, isolation_level=None)
    migrate(connection, path, migrations.load()[:1])
    connection.execute("INSERT INTO conta (nome, cor) VALUES ('a', '#fff')")
    connection.execute("INSERT INTO categoria (nome) VALUES ('home')")
    connection.execute(
        "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id)"
        " VALUES ('2026-11-01', 'x', 100, 'despesa', 1, 1)"
    )
    connection.close()
    db = Database.open(path)
    assert db.version >= 2
    assert db.list_categories()[0].recurring is False
    assert db.month_entries(Month(2026, 11))[0].recurrence_group is None
    assert (tmp_path / "money.before-v2.sqlite").exists()
    db.close()


async def test_ui_new_recurring_category_and_navigation(db):
    db.create_account("itaú", "#ff7a00")
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "1500 rent #housing @itaú"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, YesOrNo)
        await pilot.press("enter")  # create category
        await pilot.pause()
        assert isinstance(app.screen, YesOrNo)
        await pilot.press("enter")  # repeat every month
        await pilot.pause()
        assert db.category_by_name("housing").recurring
        await pilot.press("escape")
        await pilot.press("right", "right")
        await pilot.pause()
        assert len(db.month_entries(Month(2027, 1))) == 1
        table = app.query_one("#entries", DataTable)
        assert "↻" in str(table.get_row_at(0)[1])


async def test_ui_installments_in_a_recurring_category_are_refused(db):
    db.create_account("itaú", "#ff7a00")
    db.create_category("housing", recurring=True)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "100 sofa #housing @itaú 3x"
        await pilot.press("enter")
        await pilot.pause()
        assert "already repeats every month" in str(app.query_one("#preview", Static).render())
        assert db.month_entries(Month(2026, 11)) == []


async def test_ui_delete_asks_and_ends(db):
    _series(db, dt.date(2026, 11, 4))
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("right")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, OnlyThisOrUpcoming)
        await pilot.press("u")
        await pilot.pause()
        assert db.month_entries(Month(2026, 12)) == []
        assert len(db.month_entries(Month(2026, 11))) == 1


async def test_ui_limit_of_months_ahead(db):
    _series(db, dt.date(2026, 11, 4))
    app = KotsuApp(db, today=TODAY)
    async with app.run_test():
        app.month = Month(2026, 11).add(MONTHS_AHEAD + 10)
        app.refresh_all(top=True)
        assert db.month_entries(Month(2026, 11).add(MONTHS_AHEAD + 5)) == []
        assert len(db.month_entries(Month(2026, 11).add(MONTHS_AHEAD))) == 1
