"""Themes (D37): switching with `t`, theme.toml, default and amount colors."""

import datetime as dt

from textual.widgets import Static

from kotsu.domain.models import Kind, NewEntry
from kotsu.storage import preferences
from kotsu.ui import colors
from kotsu.ui.app import KotsuApp
from kotsu.ui.themes import COTTON_CANDY_LIGHT, COTTON_CANDY_NIGHT, THEMES, theme_by_name

TODAY = dt.date(2026, 11, 8)


def _with_data(db):
    account = db.create_account("nubank", "#8a2be2")
    db.create_account("inter", "#1f8fff")
    db.insert_entries([NewEntry(dt.date(2026, 11, 7), "groceries", 8990, Kind.EXPENSE, account.id)])


def test_unknown_or_missing_theme_falls_back_to_default():
    assert theme_by_name(None) is COTTON_CANDY_NIGHT
    assert theme_by_name("does-not-exist") is COTTON_CANDY_NIGHT
    assert theme_by_name("cotton-candy-light") is COTTON_CANDY_LIGHT


def test_names_from_older_versions_still_work():
    assert theme_by_name("algodao-claro") is COTTON_CANDY_LIGHT
    assert theme_by_name("algodao-noite") is COTTON_CANDY_NIGHT


def test_preferences_save_and_read(tmp_path):
    assert preferences.read_theme(tmp_path) is None
    assert preferences.save_theme(tmp_path, "cotton-candy-light")
    assert preferences.read_theme(tmp_path) == "cotton-candy-light"
    assert not list(tmp_path.glob("*.tmp"))


def test_old_tema_toml_is_read_and_replaced_on_save(tmp_path):
    (tmp_path / preferences.LEGACY_FILE_NAME).write_text('tema = "algodao-claro"\n', "utf-8")
    assert theme_by_name(preferences.read_theme(tmp_path)) is COTTON_CANDY_LIGHT
    assert preferences.save_theme(tmp_path, "cotton-candy-night")
    assert not (tmp_path / preferences.LEGACY_FILE_NAME).exists()
    assert preferences.read_theme(tmp_path) == "cotton-candy-night"


def test_damaged_file_does_not_stop_opening(tmp_path):
    (tmp_path / preferences.FILE_NAME).write_text("theme = [", encoding="utf-8")
    assert preferences.read_theme(tmp_path) is None
    (tmp_path / preferences.FILE_NAME).write_text("theme = 3\n", encoding="utf-8")
    assert preferences.read_theme(tmp_path) is None


def test_impossible_folder_does_not_raise(tmp_path):
    file = tmp_path / "file"
    file.write_text("x")
    assert not preferences.save_theme(file / "inside", "cotton-candy-light")


async def test_opens_in_night_theme_and_t_cycles_and_saves(db, tmp_path):
    _with_data(db)
    app = KotsuApp(db, today=TODAY, theme_folder=tmp_path)
    async with app.run_test() as pilot:
        assert app.theme == "cotton-candy-night" and colors.INCOME == COTTON_CANDY_NIGHT.income
        await pilot.press("t")
        assert app.theme == "cotton-candy-light" and colors.EXPENSE == COTTON_CANDY_LIGHT.expense
        assert preferences.read_theme(tmp_path) == "cotton-candy-light"
        await pilot.press("t")
        assert app.theme == "cotton-candy-night"
        assert preferences.read_theme(tmp_path) == "cotton-candy-night"


async def test_remembers_the_theme_when_opening_again(db, tmp_path):
    preferences.save_theme(tmp_path, "cotton-candy-light")
    app = KotsuApp(db, today=TODAY, theme_folder=tmp_path)
    async with app.run_test():
        assert app.theme == "cotton-candy-light"


async def test_without_folder_switches_but_does_not_save(db, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("t")
        assert app.theme == "cotton-candy-light"
    assert not list(tmp_path.iterdir())


async def test_switch_keeps_content_and_t_does_not_disturb_the_line(db, tmp_path):
    _with_data(db)
    app = KotsuApp(db, today=TODAY, theme_folder=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("t")
        top = str(app.query_one("#top", Static).render())
        accounts = str(app.query_one("#accounts", Static).render())
        assert "89,90" in top and "November 2026" in top
        assert "zeroed" in accounts and "inter" in accounts
        await pilot.press("l")  # with the line open, "t" is text, not a theme switch
        await pilot.press("t")
        assert app.theme == "cotton-candy-light"


def test_every_theme_has_distinct_colors_and_unique_name():
    assert len({t.name for t in THEMES}) == len(THEMES)
    for t in THEMES:
        assert t.income != t.expense and t.background != t.text
