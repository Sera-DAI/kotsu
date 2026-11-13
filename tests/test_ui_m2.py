"""M2 main screen: accounts, filter, copy, edit, pagination (criteria 1 to 11)."""

import datetime as dt

from textual.widgets import DataTable, Input, Static

from kotsu.domain.models import Installment, Kind, NewEntry
from kotsu.domain.month import Month
from kotsu.ui.app import PAGE_SIZE, KotsuApp
from kotsu.ui.dialogs import OnlyThisOrAll, PickColor

TODAY = dt.date(2026, 11, 8)
NOV = Month(2026, 11)


def _text(app, selector) -> str:
    return str(app.query_one(selector, Static).render())


def _base(db):
    nubank = db.create_account("nubank", "#8a2be2")
    itau = db.create_account("itaú", "#ff7a00")
    db.create_account("idle", "#1f8fff")
    home = db.create_category("home")
    db.create_category("nubank")  # same name as an account: the bare filter asks for one
    db.insert_entries(
        [
            NewEntry(dt.date(2026, 11, 5), "salary", 350000, Kind.INCOME, itau.id),
            NewEntry(dt.date(2026, 11, 6), "power", 20000, Kind.EXPENSE, itau.id, home.id),
            NewEntry(dt.date(2026, 11, 7), "groceries", 8990, Kind.EXPENSE, nubank.id),
            NewEntry(dt.date(2026, 10, 7), "sofa", 50000, Kind.EXPENSE, nubank.id, home.id),
        ]
    )
    return nubank, itau, home


async def test_top_and_one_line_per_account_with_activity(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test():
        top = _text(app, "#top")
        assert "3.500,00" in top and "289,90" in top and "3 entries" in top
        lines = _text(app, "#accounts").splitlines()
        assert len(lines) == 3  # every account, in name order (D29)
        assert "idle" in lines[0] and "zeroed" in lines[0] and "income" not in lines[0]
        assert "itaú" in lines[1] and "3.500,00" in lines[1] and "200,00" in lines[1]
        assert "nubank" in lines[2] and "89,90" in lines[2]


async def test_category_filter_applies_to_everything_and_carries_to_other_month(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("slash")
        field = app.query_one("#line", Input)
        assert field.display and app.focused is field
        field.value = "#home"
        await pilot.pause()
        assert "show only #home" in _text(app, "#preview")
        await pilot.press("enter")
        await pilot.pause()
        assert not field.display
        table = app.query_one("#entries", DataTable)
        assert table.row_count == 1 and "power" in str(table.get_row_at(0)[1])
        top = _text(app, "#top")
        assert "filter: #home" in top and "1 entry" in top and "3.500" not in top
        accounts = _text(app, "#accounts").splitlines()  # nubank has no #home in November
        assert len(accounts) == 3 and "zeroed" in accounts[2] and "200,00" in accounts[1]

        await pilot.press("left")  # October: the filter stays
        assert "sofa" in str(table.get_row_at(0)[1]) and "filter: #home" in _text(app, "#top")

        await pilot.press("escape")  # Esc on the main screen removes the filter
        await pilot.pause()
        assert not app.filter.active and "filter" not in _text(app, "#top")


async def test_filter_errors_and_empty_enter(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("slash")
        field = app.query_one("#line", Input)
        field.value = "nubank"
        await pilot.pause()
        assert "use @nubank or #nubank" in _text(app, "#preview")
        field.value = "@nothing"
        await pilot.press("enter")
        await pilot.pause()
        assert "there is no account nothing" in _text(app, "#preview") and not app.filter.active

        field.value = "itaú"  # no prefix: only the account exists
        await pilot.press("enter")
        await pilot.pause()
        assert app.filter.account_id == db.account_by_name("itaú").id
        assert len(_text(app, "#accounts").splitlines()) == 1  # account filter: only that one
        assert app.query_one("#entries", DataTable).row_count == 2

        await pilot.press("slash")
        assert field.value == "itaú"  # reopens with the current filter
        field.value = ""
        await pilot.press("enter")
        await pilot.pause()
        assert not app.filter.active
        assert app.query_one("#entries", DataTable).row_count == 3


async def test_filter_without_results_warns(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("slash")
        app.query_one("#line", Input).value = "@idle"
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one("#empty", Static).display
        assert "Esc removes the filter" in _text(app, "#empty")


async def test_copy_fills_without_date_and_creates_a_new_one(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("left", "c")  # October: copies the sofa to today
        field = app.query_one("#line", Input)
        assert field.value == "500,00 sofa #home @nubank"
        assert "08/11/2026" in _text(app, "#preview")
        await pilot.press("enter")
        await pilot.pause()
    assert [x.description for x in db.month_entries(NOV)].count("sofa") == 1
    assert len(db.month_entries(Month(2026, 10))) == 1


async def test_edit_changes_the_same_entry(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        table = app.query_one("#entries", DataTable)
        await pilot.press("down")  # 2nd row: power (06/11)
        await pilot.press("e")
        await pilot.pause()
        field = app.query_one("#line", Input)
        assert field.value == "200,00 power #home @itaú 06/11/2026"
        field.value = "210,50 power #home @new 04/11/2026"
        await pilot.pause()
        assert "edit:" in _text(app, "#preview") and "@new (new)" in _text(app, "#preview")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PickColor)
        await pilot.press("enter")
        await pilot.pause()
        assert not field.display and "edited" in _text(app, "#preview")
        # The cursor follows the edited entry, which is now the oldest of the month.
        assert "power" in str(table.get_row_at(table.cursor_row)[1])
    items = db.month_entries(NOV)
    assert len(items) == 3
    power = next(x for x in items if x.description == "power")
    assert (power.amount, power.date) == (21050, dt.date(2026, 11, 4))
    assert power.account_id == db.account_by_name("new").id


async def test_edit_all_installments_and_errors(db):
    nubank, itau, _ = _base(db)
    group = db.new_installment_group()
    db.insert_entries(
        [
            NewEntry(
                dt.date(2026, 11 + i, 20),
                "tv",
                10000,
                Kind.EXPENSE,
                nubank.id,
                installment=Installment(group, i + 1, 2),
            )
            for i in range(2)
        ]
    )
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("e")  # 1st row: tv 1/2 (20/11)
        await pilot.pause()
        assert isinstance(app.screen, OnlyThisOrAll)
        await pilot.press("enter")  # all
        await pilot.pause()
        field = app.query_one("#line", Input)
        assert field.value == "100,00 tv @nubank"
        assert "all 2 installments" in _text(app, "#preview")
        field.value = "100,00 tv @nubank 3x"
        await pilot.pause()
        assert "installments does not change" in _text(app, "#preview")
        field.value = "100,00 tv @nubank 01/11"
        await pilot.press("enter")
        await pilot.pause()
        assert "the date only changes on a single entry" in _text(app, "#preview")
        field.value = "150 television @itaú"
        await pilot.press("enter")
        await pilot.pause()
        assert "2 installments" in _text(app, "#preview")
    for i, month in enumerate([NOV, NOV.next()]):
        tv = next(x for x in db.month_entries(month) if x.installment)
        assert (tv.description, tv.amount, tv.account_id) == ("television", 15000, itau.id)
        assert tv.date.day == 20 and tv.installment.number == i + 1


async def test_esc_while_editing_changes_nothing(db):
    _base(db)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("e")
        app.query_one("#line", Input).value = "1 x @itaú"
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("l")
        assert "edit" not in _text(app, "#preview")
    assert db.month_entries(NOV)[0].description == "groceries"


async def test_long_list_loads_the_next_page(db):
    nubank = db.create_account("nubank", "#8a2be2")
    total = PAGE_SIZE + 50
    db.insert_entries(
        [
            NewEntry(dt.date(2026, 11, 1 + i % 28), f"item {i}", 100, Kind.EXPENSE, nubank.id)
            for i in range(total)
        ]
    )
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        table = app.query_one("#entries", DataTable)
        assert table.row_count == PAGE_SIZE and f"{total} entries" in _text(app, "#top")
        await pilot.press("ctrl+end")
        await app.workers.wait_for_complete()
        await pilot.pause(0.1)
        assert table.row_count == total
        # Renaming down there keeps the cursor on the same item, even after reloading.
        target = table.cursor_row
        app.refresh_all()
        assert table.cursor_row == target and table.row_count == total
