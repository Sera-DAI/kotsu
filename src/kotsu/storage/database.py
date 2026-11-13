"""SQLite connection, migrations and atomic writes.

Every write goes through `Database.transaction()`: either everything is saved, or nothing.
Before migrating a database that already has data, a copy is made next to it.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from kotsu.domain.filter import NO_FILTER, Filter
from kotsu.domain.merge import month_uid, stamp
from kotsu.domain.models import (
    Account,
    Category,
    Entry,
    Installment,
    Kind,
    NewEntry,
    Scope,
)
from kotsu.domain.month import Month
from kotsu.domain.recurrence import date_in_month, months_to_generate
from kotsu.domain.totals import MonthTotals
from kotsu.storage import migrations


def _connect(path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)  # explicit transactions
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    return connection.execute("PRAGMA user_version").fetchone()[0]


def copy_database(source: sqlite3.Connection, target: Path) -> None:
    """Consistent copy of the open database (SQLite backup API)."""
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()


def copy_database_file(source: Path, target: Path) -> None:
    """Copies a closed database to a new path, consistently."""
    connection = sqlite3.connect(source)
    try:
        copy_database(connection, target)
    finally:
        connection.close()


def migrate(
    connection: sqlite3.Connection,
    path: Path | None,
    available: Sequence[migrations.Migration] | None = None,
) -> int:
    """Applies the pending migrations, each in its own transaction. Returns the final version."""
    all_migrations = migrations.load() if available is None else available
    current = schema_version(connection)
    pending = [m for m in all_migrations if m.version > current]
    if current > len(all_migrations):
        raise RuntimeError(
            f"database at version {current}, but this Kotsu only knows up to {len(all_migrations)}"
        )
    if pending and current > 0 and path is not None:
        copy_database(connection, path.with_name(f"{path.stem}.before-v{current + 1}.sqlite"))
    for migration in pending:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in _statements(migration.sql):
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {migration.version}")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    return schema_version(connection)


def _statements(sql: str) -> list[str]:
    """Splits a script into complete statements (without executescript, which COMMITs)."""
    statements, current = [], ""
    for line in sql.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            if current.strip():
                statements.append(current)
            current = ""
    rest = [
        line for line in current.splitlines() if line.strip() and not line.strip().startswith("--")
    ]
    if rest:
        raise ValueError("migration ends with an incomplete statement")
    return statements


class Database:
    def __init__(
        self,
        connection: sqlite3.Connection,
        path: Path | None,
        backups_folder: Path | None = None,
    ) -> None:
        self._connection = connection
        self.path = path
        self.backups_folder = backups_folder  # None: `backups/` next to the database
        # Wall clock in milliseconds; tests swap it for a fixed clock.
        self.now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000

    @classmethod
    def open(cls, path: Path, backups_folder: Path | None = None) -> Database:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = _connect(path)
        try:
            migrate(connection, path)
        except BaseException:
            connection.close()
            raise
        return cls(connection, path, backups_folder)

    @classmethod
    def in_memory(cls) -> Database:
        connection = _connect(":memory:")
        migrate(connection, None)
        return cls(connection, None)

    def close(self) -> None:
        self._connection.close()

    def manual_backup(self, now: dt.datetime | None = None) -> Path | None:
        from kotsu.storage.backup import manual_backup

        if self.path is None:
            return None
        try:
            return manual_backup(
                self._connection, self.path, now or dt.datetime.now(), self.backups_folder
            )
        except sqlite3.Error:
            raise OSError("could not copy the SQLite database") from None

    @property
    def version(self) -> int:
        return schema_version(self._connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """For reads from other `storage` modules. Writes: `transaction()`."""
        return self._connection

    @property
    def replica(self) -> str:
        """Identifier of this database across devices (D39); breaks ties between stamps."""
        return self._meta("replica")

    def _meta(self, key: str) -> str:
        return self._connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()[
            0
        ]

    def stamp(self, c: sqlite3.Connection, seen: str | None = None) -> str:
        """New stamp for the changes in this transaction (D39): always larger than the ones
        already issued here and than `seen` (the largest stamp of a merged file)."""
        last = max(self._meta("clock"), seen or "")
        new = stamp(self.now_ms(), last, self.replica)
        c.execute("UPDATE meta SET value = ? WHERE key = 'clock'", (new,))
        return new

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Everything inside the block is saved together, or nothing is saved."""
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

    # --- accounts and categories ---------------------------------------------

    def create_account(self, name: str, color: str) -> Account:
        with self.transaction() as c:
            cursor = c.execute(
                "INSERT INTO account (name, color, uid, changed_at) VALUES (?, ?, ?, ?)",
                (name.strip(), color, uuid.uuid4().hex, self.stamp(c)),
            )
        return Account(cursor.lastrowid, name.strip(), color)

    def list_accounts(self) -> list[Account]:
        rows = self._connection.execute("SELECT id, name, color FROM account ORDER BY name")
        return [Account(*row) for row in rows]

    def create_category(self, name: str, recurring: bool = False) -> Category:
        with self.transaction() as c:
            cursor = c.execute(
                "INSERT INTO category (name, recurring, uid, changed_at) VALUES (?, ?, ?, ?)",
                (name.strip(), int(recurring), uuid.uuid4().hex, self.stamp(c)),
            )
        return Category(cursor.lastrowid, name.strip(), recurring)

    def list_categories(self) -> list[Category]:
        rows = self._connection.execute("SELECT id, name, recurring FROM category ORDER BY name")
        return [Category(id_, name, bool(rec)) for id_, name, rec in rows]

    def set_recurring(self, category_id: int, recurring: bool) -> None:
        """Marks or unmarks the category (D36). Series already running do not change."""
        with self.transaction() as c:
            c.execute(
                "UPDATE category SET recurring = ?, changed_at = ? WHERE id = ?",
                (int(recurring), self.stamp(c), category_id),
            )

    def account_by_name(self, name: str) -> Account | None:
        """Case-insensitive lookup, accented letters included (Itaú = ITAÚ)."""
        target = name.strip().casefold()
        return next((a for a in self.list_accounts() if a.name.casefold() == target), None)

    def category_by_name(self, name: str) -> Category | None:
        target = name.strip().casefold()
        return next((c for c in self.list_categories() if c.name.casefold() == target), None)

    # --- entries -------------------------------------------------------------

    @staticmethod
    def new_installment_group() -> str:
        return uuid.uuid4().hex

    def insert_entries(self, new_entries: Sequence[NewEntry]) -> list[int]:
        """Inserts several entries (e.g. all installments) in a single transaction."""
        ids = []
        with self.transaction() as c:
            now = self.stamp(c)
            for n in new_entries:
                if n.recurrence_group:
                    _insert_recurrence(c, n.recurrence_group, n, now)
                ids.append(_insert(c, n, now))
        return ids

    def make_recurring(self, id_: int) -> bool:
        """Makes the entry the start of a monthly series (D36). False if it is already an
        installment or already recurring."""
        item = self.entry(id_)
        if item is None or item.installment or item.recurrence_group:
            return False
        group = self.new_installment_group()
        with self.transaction() as c:
            now = self.stamp(c)
            _insert_recurrence(c, group, item, now)
            c.execute(
                "UPDATE entry SET recurrence_group = ?, changed_at = ? WHERE id = ?",
                (group, now, id_),
            )
        return True

    def extend_recurrences(self, until: Month) -> int:
        """Generates the missing months of the active series, up to `until` (D36). Returns
        how many.

        Only moves forward: a month deleted with "only this one" never comes back, and an
        ended series generates nothing. The generated month has a fixed `uid` (series +
        month) and the series template's stamp, so two devices generate the same record and
        any edit or deletion wins (D39).
        """
        series = self._connection.execute(
            "SELECT group_id, day, description, amount, kind, account_id, category_id,"
            " generated_until, changed_at"
            " FROM recurrence WHERE ended = 0 AND generated_until < ?",
            (until.start.isoformat(),),
        ).fetchall()
        if not series:
            return 0
        created = 0
        with self.transaction() as c:
            for group, day, description, amount, kind, account_id, category_id, gen, at in series:
                for month in months_to_generate(Month.of(dt.date.fromisoformat(gen)), until):
                    uid = month_uid(group, month.year, month.month)
                    if c.execute(
                        "SELECT 1 FROM entry WHERE uid = ?1"
                        " UNION ALL SELECT 1 FROM tombstone WHERE uid = ?1",
                        (uid,),
                    ).fetchone():
                        continue  # already came from another device, or was deleted there
                    _insert(
                        c,
                        NewEntry(
                            date_in_month(day, month),
                            description,
                            amount,
                            Kind(kind),
                            account_id,
                            category_id,
                            recurrence_group=group,
                        ),
                        at,
                        uid=uid,
                        generated=True,
                    )
                    created += 1
                c.execute(
                    "UPDATE recurrence SET generated_until = ? WHERE group_id = ?",
                    (until.start.isoformat(), group),
                )
        return created

    def month_entries(
        self, month: Month, limit: int = 200, offset: int = 0, filter: Filter = NO_FILTER
    ) -> list[Entry]:
        """One page of the month, most recent first. `offset` is how many to skip."""
        where, params = _month_where(month, filter)
        rows = self._connection.execute(
            f"SELECT {_ENTRY_COLUMNS} FROM entry WHERE {where}"
            " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [_entry(row) for row in rows]

    def entry(self, id_: int) -> Entry | None:
        row = self._connection.execute(
            f"SELECT {_ENTRY_COLUMNS} FROM entry WHERE id = ?", (id_,)
        ).fetchone()
        return _entry(row) if row else None

    def delete(self, id_: int, scope: Scope = Scope.ALL) -> int:
        """Deletes the entry; if it is an installment and the scope is ALL, the whole
        purchase (D12).

        Returns how many entries were removed.
        """
        where, params = self._target(id_, scope)
        with self.transaction() as c:
            now = self.stamp(c)
            if scope is Scope.UPCOMING:  # ends the series; past months stay (D36)
                c.execute(
                    "UPDATE recurrence SET ended = 1, changed_at = ? WHERE group_id = ?",
                    (now, params[0]),
                )
            c.execute(  # tombstone: the deleted entry does not come back on merge (D39)
                "INSERT OR REPLACE INTO tombstone (uid, deleted_at)"
                f" SELECT uid, ? FROM entry WHERE {where}",
                (now, *params),
            )
            return c.execute(f"DELETE FROM entry WHERE {where}", params).rowcount

    def rename(self, id_: int, description: str, scope: Scope = Scope.ALL) -> int:
        """Changes the description; with an installment and scope ALL, of every installment
        (D12)."""
        where, params = self._target(id_, scope)
        with self.transaction() as c:
            now = self.stamp(c)
            if scope is Scope.UPCOMING:
                c.execute(
                    "UPDATE recurrence SET description = ?, changed_at = ? WHERE group_id = ?",
                    (description.strip(), now, params[0]),
                )
            return c.execute(
                f"UPDATE entry SET description = ?, changed_at = ?, generated = 0 WHERE {where}",
                (description.strip(), now, *params),
            ).rowcount

    def edit(self, id_: int, new: NewEntry, scope: Scope = Scope.ALL) -> int:
        """Changes amount, kind, description, account and category (D28).

        The date only changes when the target is a single entry; for ALL installments and for
        UPCOMING the dates stay as they are (UPCOMING also changes the series template, D36).
        Installment number and group never change. Returns how many changed.
        """
        where, params = self._target(id_, scope)
        fields = "description = ?, amount = ?, kind = ?, account_id = ?, category_id = ?"
        values: list = [new.description.strip(), new.amount, new.kind.value, new.account_id]
        values.append(new.category_id)
        if where.startswith("id"):
            fields += ", date = ?"
            values.append(new.date.isoformat())
        with self.transaction() as c:
            now = self.stamp(c)
            if scope is Scope.UPCOMING:
                c.execute(
                    "UPDATE recurrence SET description = ?, amount = ?, kind = ?, account_id = ?,"
                    " category_id = ?, changed_at = ? WHERE group_id = ?",
                    (*values[:5], now, params[0]),
                )
            return c.execute(
                f"UPDATE entry SET {fields}, changed_at = ?, generated = 0 WHERE {where}",
                (*values, now, *params),
            ).rowcount

    def _target(self, id_: int, scope: Scope) -> tuple[str, tuple]:
        item = self.entry(id_)
        if item is not None and item.installment and scope is Scope.ALL:
            return "installment_group = ?", (item.installment.group,)
        if item is not None and item.recurrence_group and scope is Scope.UPCOMING:
            return "recurrence_group = ? AND date >= ?", (
                item.recurrence_group,
                item.date.isoformat(),
            )
        return "id = ?", (id_,)

    def month_totals(self, month: Month, filter: Filter = NO_FILTER) -> MonthTotals:
        where, params = _month_where(month, filter)
        row = self._connection.execute(
            f"SELECT {_SUMS} FROM entry WHERE {where}", params
        ).fetchone()
        return MonthTotals(*row)

    def totals_by_account(self, month: Month, filter: Filter = NO_FILTER) -> dict[int, MonthTotals]:
        """Income and expenses of each account that had an entry in the month (D9, D29)."""
        where, params = _month_where(month, filter)
        rows = self._connection.execute(
            f"SELECT account_id, {_SUMS} FROM entry WHERE {where} GROUP BY account_id",
            params,
        )
        return {account_id: MonthTotals(*rest) for account_id, *rest in rows}


_ENTRY_COLUMNS = (
    "id, date, description, amount, kind, account_id, category_id,"
    " installment_group, installment_number, installment_total, recurrence_group"
)

_SUMS = (
    "coalesce(sum(CASE WHEN kind = 'income' THEN amount END), 0),"
    " coalesce(sum(CASE WHEN kind = 'expense' THEN amount END), 0),"
    " count(*)"
)


def _month_where(month: Month, filter: Filter) -> tuple[str, tuple]:
    """The month's date range (uses the index) plus the filter, if any."""
    where = "date >= ? AND date < ?"
    params: list = [month.start.isoformat(), month.end_exclusive.isoformat()]
    if filter.account_id is not None:
        where += " AND account_id = ?"
        params.append(filter.account_id)
    if filter.category_id is not None:
        where += " AND category_id = ?"
        params.append(filter.category_id)
    return where, tuple(params)


def _insert_recurrence(c: sqlite3.Connection, group: str, item: NewEntry | Entry, now: str) -> None:
    c.execute(
        "INSERT INTO recurrence (group_id, day, description, amount, kind, account_id,"
        " category_id, generated_until, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            group,
            item.date.day,
            item.description,
            item.amount,
            item.kind.value,
            item.account_id,
            item.category_id,
            Month.of(item.date).start.isoformat(),
            now,
        ),
    )


def _insert(
    c: sqlite3.Connection,
    n: NewEntry,
    changed_at: str,
    uid: str | None = None,
    generated: bool = False,
) -> int:
    i = n.installment
    return c.execute(
        "INSERT INTO entry (date, description, amount, kind, account_id, category_id,"
        " installment_group, installment_number, installment_total, recurrence_group,"
        " uid, changed_at, generated)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            n.date.isoformat(),
            n.description,
            n.amount,
            n.kind.value,
            n.account_id,
            n.category_id,
            i.group if i else None,
            i.number if i else None,
            i.total if i else None,
            n.recurrence_group,
            uid or uuid.uuid4().hex,
            changed_at,
            int(generated),
        ),
    ).lastrowid


def _entry(row: tuple) -> Entry:
    (id_, date, description, amount, kind, account_id, category_id, group, number, total, rec) = row
    installment = Installment(group, number, total) if group is not None else None
    return Entry(
        id_,
        dt.date.fromisoformat(date),
        description,
        amount,
        Kind(kind),
        account_id,
        category_id,
        installment,
        rec,
    )
