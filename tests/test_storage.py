import datetime as dt
import sqlite3

import pytest

from kotsu.domain.models import Installment, Kind, NewEntry
from kotsu.domain.month import Month
from kotsu.domain.totals import MonthTotals
from kotsu.storage import migrations
from kotsu.storage.database import Database, migrate, schema_version

NOV = Month(2026, 11)


def _expense(amount, account_id, day=8, **extra):
    return NewEntry(dt.date(2026, 11, day), "groceries", amount, Kind.EXPENSE, account_id, **extra)


def test_new_database_is_at_the_latest_version(tmp_path):
    path = tmp_path / "data" / "kotsu.sqlite"
    d = Database.open(path)
    assert d.version == len(migrations.load()) >= 1
    d.close()
    assert path.exists()
    # Opening again reapplies nothing and makes no copy.
    Database.open(path).close()
    assert list(tmp_path.joinpath("data").glob("*.before-*")) == []


def test_copy_before_migrating_a_database_with_data(tmp_path):
    path = tmp_path / "kotsu.sqlite"
    d = Database.open(path)
    d.insert_entries([_expense(8990, d.create_account("Nubank", "#8a2be2").id)])
    d.close()

    real = migrations.load()
    new = migrations.Migration(len(real) + 1, "test.sql", "ALTER TABLE account ADD extra TEXT;")
    connection = sqlite3.connect(path, isolation_level=None)
    assert migrate(connection, path, [*real, new]) == new.version
    connection.close()

    copy = tmp_path / f"kotsu.before-v{new.version}.sqlite"
    assert copy.exists()
    old = sqlite3.connect(copy)
    assert schema_version(old) == len(real)
    assert old.execute("SELECT count(*) FROM entry").fetchone()[0] == 1
    old.close()


def test_failing_migration_leaves_no_trace(tmp_path):
    path = tmp_path / "kotsu.sqlite"
    Database.open(path).close()
    real = migrations.load()
    broken = migrations.Migration(
        len(real) + 1,
        "broken.sql",
        "ALTER TABLE account ADD extra TEXT;\nSELECT * FROM table_that_does_not_exist;",
    )
    connection = sqlite3.connect(path, isolation_level=None)
    with pytest.raises(sqlite3.OperationalError):
        migrate(connection, path, [*real, broken])
    assert schema_version(connection) == len(real)
    columns = [c[1] for c in connection.execute("PRAGMA table_info(account)")]
    assert "extra" not in columns
    connection.close()


def test_migration_0004_translates_a_v3_database_without_losing_anything(tmp_path):
    """A database written by the Portuguese versions (schema 3) opens with English names."""
    path = tmp_path / "kotsu.sqlite"
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    migrate(connection, path, migrations.load()[:3])
    connection.executescript(
        """
        INSERT INTO conta (nome, cor, uid, alterado_em)
            VALUES ('Itaú', '#ff7a00', 'c1', '0000000000005-0000-aaaaaaaa');
        INSERT INTO categoria (nome, recorrente, uid, alterado_em)
            VALUES ('aluguel', 1, 'g1', '0000000000005-0000-aaaaaaaa');
        INSERT INTO recorrencia (grupo, dia, descricao, valor, tipo, conta_id, categoria_id,
                                 gerada_ate, encerrada, alterado_em)
            VALUES ('s1', 5, 'aluguel', 100000, 'despesa', 1, 1, '2026-11-01', 0,
                    '0000000000006-0000-aaaaaaaa');
        INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id,
                                grupo_recorrencia, uid, alterado_em)
            VALUES ('2026-11-05', 'aluguel', 100000, 'despesa', 1, 1, 's1', 'l1',
                    '0000000000006-0000-aaaaaaaa');
        INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, grupo_parcela,
                                parcela_numero, parcela_total, uid, alterado_em)
            VALUES ('2026-11-08', 'salário', 350000, 'receita', 1, 'p1', 1, 2, 'l2',
                    '0000000000007-0000-aaaaaaaa');
        INSERT INTO lapide (uid, excluido_em) VALUES ('l9', '0000000000008-0000-aaaaaaaa');
        UPDATE meta SET valor = '0000000000008-0000-aaaaaaaa' WHERE chave = 'relogio';
        """
    )
    replica = connection.execute("SELECT valor FROM meta WHERE chave = 'replica'").fetchone()[0]
    connection.close()

    d = Database.open(path)
    try:
        assert d.version == len(migrations.load())
        assert (tmp_path / "kotsu.before-v4.sqlite").exists()
        assert d.replica == replica
        assert [(a.name, a.color) for a in d.list_accounts()] == [("Itaú", "#ff7a00")]
        assert [(c.name, c.recurring) for c in d.list_categories()] == [("aluguel", True)]
        assert d.month_totals(NOV) == MonthTotals(350000, 100000, 2)
        rent, salary = sorted(d.month_entries(NOV), key=lambda e: e.amount)
        assert rent.recurrence_group == "s1" and rent.kind is Kind.EXPENSE
        assert salary.installment == Installment("p1", 1, 2) and salary.kind is Kind.INCOME
        c = d.connection
        assert c.execute("SELECT uid FROM tombstone").fetchall() == [("l9",)]
        assert (
            c.execute("SELECT value FROM meta WHERE key = 'clock'")
            .fetchone()[0]
            .startswith("0000000000008")
        )
        assert c.execute("SELECT kind, ended FROM recurrence").fetchall() == [("expense", 0)]
        # The new stamp still goes past the old clock, and new rows get a uid.
        account = d.create_account("Nubank", "#8a2be2")
        assert c.execute(
            "SELECT changed_at > '0000000000008' FROM account WHERE id = ?", (account.id,)
        ).fetchone()[0]
        c.execute("INSERT INTO category (name) VALUES ('x')")
        assert c.execute("SELECT uid FROM category WHERE name = 'x'").fetchone()[0]
        assert d.extend_recurrences(Month(2026, 12)) == 1
    finally:
        d.close()


def test_database_newer_than_the_app_refuses_to_open(tmp_path):
    path = tmp_path / "kotsu.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 999")
    connection.close()
    with pytest.raises(RuntimeError, match="999"):
        Database.open(path)


def test_installments_are_saved_all_or_none(db):
    nubank = db.create_account("Nubank", "#8a2be2")
    group = db.new_installment_group()
    good = [_expense(12000, nubank.id, installment=Installment(group, n, 3)) for n in (1, 2)]
    bad = _expense(12000, 999, installment=Installment(group, 3, 3))  # account does not exist
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_entries([*good, bad])
    assert db.month_entries(NOV) == []


def test_transaction_rolls_back_on_any_error(db):
    with pytest.raises(KeyError):
        with db.transaction() as c:
            c.execute("INSERT INTO category (name) VALUES ('home')")
            raise KeyError("boom")
    assert db.list_categories() == []


@pytest.mark.parametrize(
    ("date", "amount", "account"),
    [
        ("2026-11-08", 89.9, 1),  # amount is not an integer
        ("08/11/2026", 100, 1),  # date outside the ISO format
        ("2026-11-08", 100, None),  # no account (D21)
        ("2026-11-08", 100, 999),  # account does not exist
    ],
)
def test_schema_rejects_a_wrong_entry(db, date, amount, account):
    db.create_account("Nubank", "#8a2be2")
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as c:
        c.execute(
            "INSERT INTO entry (date, description, amount, kind, account_id)"
            " VALUES (?, 'x', ?, 'expense', ?)",
            (date, amount, account),
        )
    assert db.month_entries(NOV) == []


def test_schema_accepts_a_right_entry_and_unique_account(db):
    db.create_account("Nubank", "#8a2be2")
    with db.transaction() as c:
        c.execute(
            "INSERT INTO entry (date, description, amount, kind, account_id)"
            " VALUES ('2026-11-08', 'x', 100, 'expense', 1)"
        )
    assert len(db.month_entries(NOV)) == 1
    with pytest.raises(sqlite3.IntegrityError):
        db.create_account("nubank", "#000000")  # unique name, case-insensitive


def test_month_totals_and_list(db):
    nubank = db.create_account("Nubank", "#8a2be2")
    home = db.create_category("home")
    db.insert_entries(
        [
            NewEntry(dt.date(2026, 11, 5), "salary", 350000, Kind.INCOME, nubank.id),
            _expense(8990, nubank.id, day=1, category_id=home.id),
            _expense(5000, nubank.id, day=30),
            NewEntry(dt.date(2026, 10, 31), "october", 777, Kind.EXPENSE, nubank.id),
            NewEntry(dt.date(2026, 12, 1), "december", 777, Kind.EXPENSE, nubank.id),
        ]
    )
    assert db.month_totals(NOV) == MonthTotals(350000, 13990, 3)
    days = [x.date.day for x in db.month_entries(NOV)]
    assert days == [30, 5, 1]
    assert [x.date.day for x in db.month_entries(NOV, limit=1, offset=1)] == [5]
    assert db.month_totals(Month(2027, 1)) == MonthTotals()


def test_month_uses_the_date_index(db):
    plan = db.connection.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM entry WHERE date >= ? AND date < ?",
        ("2026-11-01", "2026-12-01"),
    ).fetchall()
    assert any("entry_date" in row[-1] for row in plan)
