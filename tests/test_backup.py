import datetime as dt
import sqlite3

import pytest

from kotsu.domain.models import Kind, NewEntry
from kotsu.domain.month import Month
from kotsu.storage.database import Database
from kotsu.ui.app import KotsuApp


def test_manual_backup_makes_a_new_copy_keeps_the_latest_five_and_restores(tmp_path):
    d = Database.open(tmp_path / "money.sqlite")
    account = d.create_account("Itaú", "#8a2be2")
    today = dt.date(2026, 11, 1)
    now = dt.datetime(2026, 11, 1, 10, 30, 5)
    try:
        d.insert_entries([NewEntry(today, "Coffee", 99, Kind.EXPENSE, account.id)])
        first = d.manual_backup(now)
        assert first.name == "money.2026-11-01-103005.sqlite"
        content = first.read_bytes()
        # Same second: a free name, without overwriting the previous copy.
        d.insert_entries([NewEntry(today, "Bread", 500, Kind.EXPENSE, account.id)])
        second = d.manual_backup(now)
        assert second.name == "money.2026-11-01-103005-2.sqlite"
        assert first.read_bytes() == content
        # Pre-migration copies and files in other formats never get pruned.
        migration = tmp_path / "money.before-v2.sqlite"
        migration.write_bytes(b"migration")
        daily = tmp_path / "backups" / "money.2026-10-01.sqlite"
        daily.write_bytes(b"old format")
        for days in range(1, 13):
            last = d.manual_backup(now + dt.timedelta(days=days))
        copies = sorted((tmp_path / "backups").glob("money.2026-1*-*-*.sqlite"))
        assert len(copies) == 5
        assert copies[0].name == "money.2026-11-09-103005.sqlite"
        assert copies[-1] == last
        assert migration.exists() and daily.exists()
        assert not list((tmp_path / "backups").glob(".backup-*"))
        restored = Database.open(last)
        try:
            assert restored.month_totals(Month(2026, 11)) == d.month_totals(Month(2026, 11))
        finally:
            restored.close()
    finally:
        d.close()


def test_copy_failure_neither_publishes_nor_removes_backups(tmp_path, monkeypatch):
    d = Database.open(tmp_path / "money.sqlite")
    try:
        d.manual_backup(dt.datetime(2026, 11, 1, 9, 0, 0))
        folder = tmp_path / "backups"
        before = {p.name: p.read_bytes() for p in folder.iterdir()}

        def fail(source, target):
            target.write_bytes(b"partial")
            raise sqlite3.OperationalError("disk full")

        monkeypatch.setattr("kotsu.storage.database.copy_database", fail)
        with pytest.raises(OSError):
            d.manual_backup(dt.datetime(2026, 11, 2, 9, 0, 0))
        assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    finally:
        d.close()


def test_in_memory_database_makes_no_backup(db):
    assert db.manual_backup() is None


async def test_app_does_not_back_up_on_its_own_and_key_b_does(tmp_path, monkeypatch):
    d = Database.open(tmp_path / "money.sqlite")
    app = KotsuApp(d)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            assert not (tmp_path / "backups").exists()
            await pilot.press("b")
            assert len(list((tmp_path / "backups").glob("money.*.sqlite"))) == 1

            def fail():
                raise OSError("no space")

            monkeypatch.setattr(d, "manual_backup", fail)
            await pilot.press("b")
            await pilot.press("right")
            assert app.month == Month.of(app.today).next()
    finally:
        d.close()


def test_pruning_sorts_numeric_suffix_as_a_number(tmp_path):
    d = Database.open(tmp_path / "money.sqlite")
    now = dt.datetime(2026, 11, 1, 10, 0, 0)
    try:
        names = [d.manual_backup(now).name for _ in range(12)]
        remaining = sorted(p.name for p in (tmp_path / "backups").iterdir())
        # The last 5 requested (-8 to -12) stay; "-2" does not beat "-10" by text order.
        assert remaining == sorted(names[-5:])
        assert names[-1].endswith("-12.sqlite")
    finally:
        d.close()
