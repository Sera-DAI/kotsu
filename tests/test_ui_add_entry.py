"""Quick line on the screen: preview, questions and deletion (criteria 8 to 10)."""

import datetime as dt

from textual.widgets import DataTable, Input, Static

from kotsu.domain.month import Month
from kotsu.ui import colors
from kotsu.ui.app import KotsuApp
from kotsu.ui.dialogs import OnlyThisOrAll, PickColor, YesOrNo

TODAY = dt.date(2026, 11, 8)


def _preview(app) -> str:
    return str(app.query_one("#preview", Static).render())


async def _type(pilot, text):
    await pilot.press(*["space" if c == " " else c for c in text])


async def test_new_account_and_category_ask_and_save(db):
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        field = app.query_one("#line", Input)
        assert field.display and app.focused is field
        field.value = "89,90 groceries #food @nubank"
        await pilot.pause()
        preview = _preview(app)
        assert "expense 89,90" in preview and "@nubank (new)" in preview
        assert "#food (new)" in preview and "08/11/2026" in preview

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PickColor)
        await pilot.press("3")  # blue
        await pilot.pause()
        assert isinstance(app.screen, YesOrNo)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, YesOrNo)  # repeat every month? (D36)
        await pilot.press("n")
        await pilot.pause()

        (item,) = db.month_entries(Month(2026, 11))
        assert (item.amount, item.description) == (8990, "groceries")
        assert db.account_by_name("nubank").color == colors.ACCOUNTS[2]
        assert db.category_by_name("food").id == item.category_id
        assert field.value == "" and app.focused is field
        assert "saved" in _preview(app)
        assert app.query_one("#entries", DataTable).row_count == 1


async def test_esc_on_the_question_saves_nothing(db):
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "10 coffee @new"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert db.list_accounts() == []
        assert db.month_entries(Month(2026, 11)) == []
        assert "nothing was saved" in _preview(app)


async def test_missing_account_always_blocks_even_after_a_previous_entry(db):
    db.create_account("nubank", "#8a2be2")
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        field = app.query_one("#line", Input)
        field.value = "5 bread @nubank"
        await pilot.press("enter")
        await pilot.pause()
        field.value = "120 10x"
        await pilot.pause()
        assert "missing @account" in _preview(app) and "nubank" not in _preview(app)
        await pilot.press("enter")
        await pilot.pause()
        assert "give the account with @name" in _preview(app)
        assert field.value == "120 10x"
    assert len(db.month_entries(Month(2026, 11))) == 1
    assert db.month_entries(Month(2026, 12)) == []


async def test_installments_through_the_screen(db):
    nubank = db.create_account("nubank", "#8a2be2")
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "120 10x @nubank"
        await pilot.pause()
        assert "10x of 120,00 = 1.200,00" in _preview(app)
        assert "Nov/2026 to Aug/2027" in _preview(app)
        await pilot.press("enter")
        await pilot.pause()
    for i in range(10):
        (item,) = db.month_entries(Month(2026, 11).add(i))
        assert (item.amount, item.account_id, item.installment.label) == (
            12000,
            nubank.id,
            f"{i + 1}/10",
        )


async def test_typing_shortcut_letters_goes_to_the_line(db):
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        await _type(pilot, "12 lqdr")
        assert app.query_one("#line", Input).value == "12 lqdr"
        assert app.is_running
        await pilot.press("escape")
        assert not app.query_one("#line", Input).display


async def test_error_shows_in_the_preview(db):
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "10 x 31/02"
        await pilot.pause()
        assert "impossible date" in _preview(app)
        await pilot.press("enter")
        await pilot.pause()
        assert db.month_entries(Month(2026, 2)) == []


async def test_deleting_an_installment_asks_and_default_is_all(db):
    nubank = db.create_account("nubank", "#8a2be2")
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "120 fridge @nubank 3x"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, OnlyThisOrAll)
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one("#empty", Static).display
    assert db.month_entries(Month(2026, 12)) == []
    assert db.account_by_name("nubank") == nubank


async def test_rename_only_this(db):
    app = KotsuApp(db, today=TODAY)
    db.create_account("nubank", "#8a2be2")
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "120 fridge @nubank 3x"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape", "r")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        app.screen.query_one(Input).value = "fridge 1"
        await pilot.press("enter")
        await pilot.pause()
    assert db.month_entries(Month(2026, 11))[0].description == "fridge 1"
    assert db.month_entries(Month(2026, 12))[0].description == "fridge"


async def test_deleting_a_single_entry_confirms(db):
    app = KotsuApp(db, today=TODAY)
    db.create_account("nubank", "#8a2be2")
    async with app.run_test() as pilot:
        await pilot.press("l")
        app.query_one("#line", Input).value = "10 coffee @nubank"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape", "d")
        await pilot.pause()
        assert isinstance(app.screen, YesOrNo)
        await pilot.press("escape")
        await pilot.pause()
        assert len(db.month_entries(Month(2026, 11))) == 1
        await pilot.press("d", "enter")
        await pilot.pause()
    assert db.month_entries(Month(2026, 11)) == []
