"""Exchange file between devices (D39): export, import (merge) and verify.

Each device has its own database. To join the data, one exports a JSON file with everything
it has and the other imports it: the merge (`domain.merge`) decides record by record.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from kotsu.domain import merge
from kotsu.domain.merge import Comparison, ExchangeError, Summary
from kotsu.storage.database import Database, copy_database

BEFORE_IMPORT_NAME = "before-import"

_SERIES_FIELDS = (
    "group",
    "day",
    "description",
    "amount",
    "kind",
    "account",
    "category",
    "generated_until",
    "ended",
    "changed_at",
)
_ENTRY_FIELDS = (
    "uid",
    "date",
    "description",
    "amount",
    "kind",
    "account",
    "category",
    "recurrence",
    "generated",
    "changed_at",
)


def read_state(database: Database) -> dict:
    """The whole content of the database, with `uid` instead of local ids."""
    c = database.connection
    accounts = [
        {"uid": uid, "name": name, "color": color, "changed_at": at}
        for uid, name, color, at in c.execute(
            "SELECT uid, name, color, changed_at FROM account ORDER BY uid"
        )
    ]
    categories = [
        {"uid": uid, "name": name, "recurring": bool(rec), "changed_at": at}
        for uid, name, rec, at in c.execute(
            "SELECT uid, name, recurring, changed_at FROM category ORDER BY uid"
        )
    ]
    recurrences = []
    for row in c.execute(
        "SELECT r.group_id, r.day, r.description, r.amount, r.kind, account.uid, category.uid,"
        " r.generated_until, r.ended, r.changed_at FROM recurrence r"
        " JOIN account ON account.id = r.account_id"
        " LEFT JOIN category ON category.id = r.category_id ORDER BY r.group_id"
    ):
        serie = dict(zip(_SERIES_FIELDS, row, strict=True))
        serie["ended"] = bool(serie["ended"])
        recurrences.append(serie)
    entries = []
    for *common, group, number, total in c.execute(
        "SELECT e.uid, e.date, e.description, e.amount, e.kind, account.uid, category.uid,"
        " e.recurrence_group, e.generated, e.changed_at,"
        " e.installment_group, e.installment_number, e.installment_total FROM entry e"
        " JOIN account ON account.id = e.account_id"
        " LEFT JOIN category ON category.id = e.category_id ORDER BY e.uid"
    ):
        entry = dict(zip(_ENTRY_FIELDS, common, strict=True))
        entry["generated"] = bool(entry["generated"])
        entry["installment"] = (
            None if group is None else {"group": group, "number": number, "total": total}
        )
        entries.append(entry)
    tombstones = [
        {"uid": uid, "deleted_at": at}
        for uid, at in c.execute("SELECT uid, deleted_at FROM tombstone ORDER BY uid")
    ]
    return {
        "accounts": accounts,
        "categories": categories,
        "recurrences": recurrences,
        "entries": entries,
        "tombstones": tombstones,
    }


def check_code(database: Database) -> str:
    """Check code of this database's data."""
    return merge.check_code(read_state(database))


def export(database: Database, target: Path, now: dt.datetime | None = None) -> str:
    """Writes the exchange file to `target` (atomic swap). Returns the check code."""
    state = read_state(database)
    code = merge.check_code(state)
    file = {
        "app": "kotsu",
        "format": merge.FORMAT,
        "replica": database.replica,
        "exported_at": (now or dt.datetime.now()).isoformat(timespec="seconds"),
        "check_code": code,
        **state,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".exchange-", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(file, out, ensure_ascii=False, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return code


def read_file(source: Path) -> dict:
    """Reads and validates an exchange file. Raises `ExchangeError` with a message for the
    person."""
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ExchangeError(f"could not read {source}: {error}") from None
    try:
        data = json.loads(text)
    except ValueError:
        raise ExchangeError(f"{source} is not a Kotsu export") from None
    return merge.validate(data)


def compare(database: Database, source: Path) -> Comparison:
    """Differences between this database and another device's file. Changes nothing."""
    return merge.compare(read_state(database), read_file(source))


def import_file(database: Database, source: Path) -> Summary:
    """Merges another device's file into this database, in a single transaction.

    Before changing anything, keeps a copy of the database in `backups/` (just one,
    replaced on every import that changes something).
    """
    remote = read_file(source)
    local = read_state(database)
    new = merge.merge(local, remote)
    seen = merge.highest_stamp(remote)
    if new == local:
        with database.transaction() as c:
            _advance_clock(c, seen)
        return Summary()
    if database.path is not None:
        folder = database.backups_folder or database.path.parent / "backups"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            copy_database(
                database.connection, folder / f"{database.path.stem}.{BEFORE_IMPORT_NAME}.sqlite"
            )
        except (OSError, sqlite3.Error) as error:
            raise ExchangeError(f"could not save the safety copy in {folder}: {error}") from None
    with database.transaction() as c:
        _apply(c, new)
        _advance_clock(c, seen)
    return merge.summarize(local, new)


def _advance_clock(c: sqlite3.Connection, seen: str) -> None:
    """The next stamp here goes past everything the file brought."""
    c.execute("UPDATE meta SET value = max(value, ?) WHERE key = 'clock'", (seen,))


def _apply(c: sqlite3.Connection, new: dict) -> None:
    """Makes the database equal to the `new` state, keeping the local ids."""
    accounts = _apply_named(c, "account", new["accounts"], ("color",))
    categories = _apply_named(c, "category", new["categories"], ("recurring",))

    for r in new["recurrences"]:
        c.execute(
            "INSERT INTO recurrence (group_id, day, description, amount, kind, account_id,"
            " category_id, generated_until, ended, changed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (group_id) DO UPDATE SET day = excluded.day,"
            " description = excluded.description, amount = excluded.amount,"
            " kind = excluded.kind, account_id = excluded.account_id,"
            " category_id = excluded.category_id, generated_until = excluded.generated_until,"
            " ended = excluded.ended, changed_at = excluded.changed_at",
            (
                r["group"],
                r["day"],
                r["description"],
                r["amount"],
                r["kind"],
                accounts[r["account"]],
                categories.get(r["category"]),
                r["generated_until"],
                int(r["ended"]),
                r["changed_at"],
            ),
        )

    local = {uid for (uid,) in c.execute("SELECT uid FROM entry")}
    alive = {x["uid"] for x in new["entries"]}
    c.executemany("DELETE FROM entry WHERE uid = ?", [(uid,) for uid in local - alive])
    for x in new["entries"]:
        i = x["installment"] or {}
        values = (
            x["date"],
            x["description"],
            x["amount"],
            x["kind"],
            accounts[x["account"]],
            categories.get(x["category"]),
            i.get("group"),
            i.get("number"),
            i.get("total"),
            x["recurrence"],
            int(x["generated"]),
            x["changed_at"],
            x["uid"],
        )
        if x["uid"] in local:
            c.execute(
                "UPDATE entry SET date = ?, description = ?, amount = ?, kind = ?,"
                " account_id = ?, category_id = ?, installment_group = ?,"
                " installment_number = ?, installment_total = ?, recurrence_group = ?,"
                " generated = ?, changed_at = ? WHERE uid = ?",
                values,
            )
        else:
            c.execute(
                "INSERT INTO entry (date, description, amount, kind, account_id, category_id,"
                " installment_group, installment_number, installment_total, recurrence_group,"
                " generated, changed_at, uid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

    c.executemany(
        "INSERT OR REPLACE INTO tombstone (uid, deleted_at) VALUES (?, ?)",
        [(x["uid"], x["deleted_at"]) for x in new["tombstones"]],
    )


def _apply_named(
    c: sqlite3.Connection, table: str, items: list[dict], fields: tuple[str, ...]
) -> dict[str, int]:
    """Saves merged accounts or categories. Returns `uid -> local id`.

    The one that exists here with the same name and another `uid` is the same one: it takes
    the `uid` the merge chose, and the entries here keep pointing to it.
    """
    by_uid, by_name = {}, {}
    for id_, uid, name in c.execute(f"SELECT id, uid, name FROM {table}").fetchall():
        by_uid[uid] = id_
        by_name[merge.name_key(name)] = id_
    ids = {}
    assignments = ", ".join(f"{field} = ?" for field in fields)
    for item in items:
        values = [int(v) if isinstance(v, bool) else v for v in (item[k] for k in fields)]
        id_ = by_uid.get(item["uid"]) or by_name.get(merge.name_key(item["name"]))
        if id_ is None:
            id_ = c.execute(
                f"INSERT INTO {table} (uid, name, changed_at, {', '.join(fields)})"
                f" VALUES (?, ?, ?{', ?' * len(fields)})",
                (item["uid"], item["name"], item["changed_at"], *values),
            ).lastrowid
        else:
            c.execute(
                f"UPDATE {table} SET uid = ?, name = ?, changed_at = ?, {assignments} WHERE id = ?",
                (item["uid"], item["name"], item["changed_at"], *values, id_),
            )
        ids[item["uid"]] = id_
    return ids
