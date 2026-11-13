"""Data exchange between devices (D39): identity, merging, file, verification."""

import datetime as dt
import json
import random
import sqlite3

import pytest

import generate_vectors
from kotsu.__main__ import main
from kotsu.domain import merge
from kotsu.domain.models import Installment, Kind, NewEntry, Scope
from kotsu.domain.month import Month
from kotsu.storage import exchange, lock, migrations
from kotsu.storage.database import Database, migrate
from kotsu.ui.app import KotsuApp

NOV = Month(2026, 11)


class Clock:
    """Wall clock the tests move forward (or back) by hand."""

    def __init__(self, ms: int) -> None:
        self.ms = ms

    def __call__(self) -> int:
        self.ms += 1
        return self.ms


def _database(start_ms: int) -> Database:
    db = Database.in_memory()
    db.now_ms = Clock(start_ms)
    return db


def _add(db, description, amount=1000, account="nubank", day=8, category=None, **others):
    account_ = db.account_by_name(account) or db.create_account(account, "#8a2be2")
    category_ = None
    if category:
        category_ = db.category_by_name(category) or db.create_category(category)
    new = NewEntry(
        dt.date(2026, 11, day),
        description,
        amount,
        Kind.EXPENSE,
        account_.id,
        category_.id if category_ else None,
        **others,
    )
    return db.insert_entries([new])[0]


def _exchange(source: Database, target: Database, tmp_path) -> merge.Summary:
    file = tmp_path / "exchange.json"
    exchange.export(source, file)
    return exchange.import_file(target, file)


def _descriptions(db, month=NOV) -> list[str]:
    return sorted(x.description for x in db.month_entries(month))


@pytest.fixture
def pc():
    db = _database(1_000_000)
    yield db
    db.close()


@pytest.fixture
def phone():
    db = _database(2_000_000)
    yield db
    db.close()


# --- cases shared with Android -------------------------------------------------------


def test_vectors_on_disk_match_the_generator():
    assert generate_vectors.out_of_date() == []


@pytest.mark.parametrize("case", generate_vectors.generate()["merge.json"], ids=lambda c: c["name"])
def test_merge_is_commutative_and_idempotent(case):
    a, b, expected = case["a"], case["b"], case["expected"]
    assert merge.merge(a, b) == expected
    assert merge.merge(b, a) == expected
    assert merge.merge(expected, a) == expected
    assert merge.merge(b, expected) == expected
    assert merge.check_code(expected) == case["expected_code"]


def test_chosen_cases_give_the_hand_written_result():
    """The vectors' outputs come from the code itself; these check the rules from outside."""
    cases = {c["name"]: c["expected"] for c in generate_vectors.generate()["merge.json"]}

    edited = cases["same entry edited on both sides: the larger stamp wins, whole"]
    assert [(x["description"], x["amount"]) for x in edited["entries"]] == [("bakery", 1500)]

    deleted = cases["deleted on one side after the other's last edit: removed"]
    assert deleted["entries"] == []
    assert [x["uid"] for x in deleted["tombstones"]] == ["l-1"]

    back = cases["edited on one side after deleted on the other: comes back"]
    assert [x["description"] for x in back["entries"]] == ["came back"]

    account = cases[
        "same account created on both sides: one remains, smallest uid and newest content"
    ]
    assert [(a["uid"], a["name"], a["color"]) for a in account["accounts"]] == [
        ("c-aa", "ITAÚ", "#0000ff")
    ]
    assert {x["account"] for x in account["entries"]} == {"c-aa"}

    series = cases["series: both sides generated the same month; one generated further"]
    assert [x["uid"] for x in series["entries"]] == ["l-1", "s-1-2026-12", "s-1-2027-01"]
    assert series["recurrences"][0]["generated_until"] == "2027-01-01"

    deleted_month = cases[
        "series: month generated on one side and deleted (only this) on the other stays deleted"
    ]
    assert deleted_month["entries"] == []

    ended = cases["series: ended on one side, older template on the other"]
    assert ended["recurrences"][0]["ended"] is True
    assert ended["recurrences"][0]["generated_until"] == "2027-03-01"


def _random_state(rng: random.Random) -> dict:
    """Small valid state. As in the app, a name does not change and equal stamp = equal content."""
    g = generate_vectors
    names = {"c1": "nu", "c2": "NU", "c3": "itaú", "c4": "x", "g1": "home", "g2": "HOME", "g3": "y"}

    def stamp() -> str:
        replica = rng.choice(["aaaaaaaa", "bbbbbbbb", "cccccccc"])
        return g._c(rng.randint(1, 6), replica, rng.randint(0, 1))

    def fixed(*key) -> random.Random:
        return random.Random(repr(key))

    def unique(uids, create):
        items, used = [], set()
        for uid in uids:
            if names[uid].casefold() not in used:
                used.add(names[uid].casefold())
                items.append(create(uid, stamp()))
        return items

    accounts = unique(
        rng.sample(["c1", "c2", "c3", "c4"], rng.randint(1, 3)),
        lambda uid, at: g.account(uid, names[uid], at, color=fixed(uid, at).choice(["#1", "#2"])),
    )
    categories = unique(
        rng.sample(["g1", "g2", "g3"], rng.randint(0, 2)),
        lambda uid, at: g.category(uid, names[uid], at, fixed(uid, at).random() < 0.5),
    )
    account_uids = [a["uid"] for a in accounts]
    category_uids = [c["uid"] for c in categories] + [None]
    series = []
    for group in rng.sample(["s1", "s2"], rng.randint(0, 2)):
        at = stamp()
        series.append(
            g.series(
                group,
                at,
                account=fixed(group, at, "c").choice(["c1", "c2", "c3", "c4"]),
                category=None,
                generated_until=rng.choice(["2026-11-01", "2027-01-01"]),
                ended=fixed(group, at).random() < 0.3,
            )
        )
    series = [s for s in series if s["account"] in account_uids]
    groups = [s["group"] for s in series] + [None]
    entries = []
    for uid in rng.sample(["l1", "l2", "l3", "l4"], rng.randint(0, 4)):
        at = stamp()
        entries.append(
            g.entry(
                uid,
                at,
                amount=fixed(uid, at).choice([1, 2, 3]),
                generated=fixed(uid, at).random() < 0.3,
                account=rng.choice(account_uids),
                category=rng.choice(category_uids),
                recurrence=rng.choice(groups),
            )
        )
    tombstones = [
        g.tombstone(uid, stamp()) for uid in rng.sample(["l1", "l2", "l3", "l4"], rng.randint(0, 2))
    ]
    return merge.validate(
        g.state(
            accounts=accounts,
            categories=categories,
            recurrences=series,
            entries=entries,
            tombstones=tombstones,
        )
    )


def test_merge_converges_in_any_order():
    """Three devices: it does not matter who merges with whom first."""
    rng = random.Random(39)
    for _ in range(1500):
        a, b, c = (_random_state(rng) for _ in range(3))
        ab = merge.merge(a, b)
        assert ab == merge.merge(b, a)
        assert merge.merge(ab, a) == ab
        assert merge.merge(ab, c) == merge.merge(a, merge.merge(b, c))


@pytest.mark.parametrize(
    "case", generate_vectors.generate()["invalid.json"], ids=lambda c: c["name"]
)
def test_invalid_file_is_refused(case):
    with pytest.raises(merge.ExchangeError) as error:
        merge.validate(case["file"])
    assert str(error.value) == case["error"]


def test_stamp_never_goes_backwards():
    last = merge.ZERO_STAMP
    for now in (50, 50, 49, 10, 51, 51):
        new = merge.stamp(now, last, "ab12cd34")
        assert new > last
        last = new
    full = "0000000000050-9999-ab12cd34"
    assert merge.stamp(50, full, "ab12cd34") == "0000000000051-0000-ab12cd34"


# --- database: identity and stamps ----------------------------------------------------


def test_migration_0003_gives_identity_to_existing_records(tmp_path):
    path = tmp_path / "money.sqlite"
    connection = sqlite3.connect(path, isolation_level=None)
    migrate(connection, path, migrations.load()[:2])
    connection.execute("INSERT INTO conta (nome, cor) VALUES ('a', '#fff'), ('b', '#000')")
    connection.execute("INSERT INTO categoria (nome) VALUES ('home')")
    connection.executemany(
        "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id)"
        " VALUES ('2026-11-01', ?, 100, 'despesa', 1, 1)",
        [("x",), ("y",), ("z",)],
    )
    connection.close()

    db = Database.open(path)
    assert db.version == len(migrations.load())
    assert (tmp_path / "money.before-v3.sqlite").exists()
    assert lock.conflicts(tmp_path, "money.sqlite") == []
    state = merge.validate({"app": "kotsu", "format": merge.FORMAT, **exchange.read_state(db)})
    assert len({x["uid"] for x in state["entries"]}) == 3
    assert len({a["uid"] for a in state["accounts"]}) == 2
    assert {x["changed_at"] for x in state["entries"]} == {merge.ZERO_STAMP}
    assert {x["kind"] for x in state["entries"]} == {"expense"}
    assert len(db.replica) == 8
    assert _descriptions(db) == ["x", "y", "z"]
    # Whoever inserts outside Database (without a uid) also gets an identity.
    with db.transaction() as c:
        c.execute(
            "INSERT INTO entry (date, description, amount, kind, account_id)"
            " VALUES ('2026-11-02', 'w', 100, 'expense', 1)"
        )
    assert len({x["uid"] for x in exchange.read_state(db)["entries"]}) == 4
    db.close()


def test_each_change_gets_a_larger_stamp_even_with_the_clock_behind(pc):
    id_ = _add(pc, "bakery")
    first = exchange.read_state(pc)["entries"][0]["changed_at"]
    pc.now_ms = Clock(5)  # the computer's clock went back in time
    pc.rename(id_, "joe's bakery")
    after = exchange.read_state(pc)["entries"][0]
    assert after["changed_at"] > first
    assert after["changed_at"].endswith(pc.replica)


def test_deleting_leaves_a_tombstone_for_each_installment(pc):
    account = pc.create_account("nubank", "#8a2be2")
    group = pc.new_installment_group()
    ids = pc.insert_entries(
        [
            NewEntry(
                dt.date(2026, 11 + i, 10),
                "tv",
                100,
                Kind.EXPENSE,
                account.id,
                None,
                Installment(group, i + 1, 2),
            )
            for i in range(2)
        ]
    )
    uids = {x["uid"] for x in exchange.read_state(pc)["entries"]}
    assert pc.delete(ids[0], Scope.ALL) == 2
    state = exchange.read_state(pc)
    assert state["entries"] == []
    assert {x["uid"] for x in state["tombstones"]} == uids


# --- two devices ----------------------------------------------------------------------


def test_first_import_copies_everything_and_the_codes_match(pc, phone, tmp_path):
    _add(pc, "bakery", category="home")
    _add(pc, "groceries", account="itaú")
    summary = _exchange(pc, phone, tmp_path)
    assert (summary.added, summary.changed, summary.removed) == (2, 0, 0)
    assert _descriptions(phone) == ["bakery", "groceries"]
    assert [a.name for a in phone.list_accounts()] == ["itaú", "nubank"]
    assert exchange.check_code(phone) == exchange.check_code(pc)
    assert phone.replica != pc.replica
    assert _exchange(pc, phone, tmp_path).nothing  # repeating changes nothing


def test_entries_from_both_sides_come_together(pc, phone, tmp_path):
    bakery = _add(pc, "bakery")
    _add(pc, "power")
    _exchange(pc, phone, tmp_path)

    # Without talking: the phone adds, deletes and creates an account; the PC renames and
    # creates the same account.
    _add(phone, "uber", account="Itaú")
    power = next(x for x in phone.month_entries(NOV) if x.description == "power")
    phone.delete(power.id)
    pc.rename(bakery, "joe's bakery")
    _add(pc, "groceries", account="itaú")
    assert exchange.check_code(pc) != exchange.check_code(phone)

    _exchange(phone, pc, tmp_path)
    _exchange(pc, phone, tmp_path)

    expected = ["groceries", "joe's bakery", "uber"]
    assert _descriptions(pc) == expected
    assert _descriptions(phone) == expected
    assert exchange.check_code(pc) == exchange.check_code(phone)
    assert exchange.read_state(pc) == exchange.read_state(phone)
    # "itaú" and "Itaú" became a single account, with the entries from both sides.
    for db in (pc, phone):
        accounts = [a for a in db.list_accounts() if a.name.casefold() == "itaú"]
        assert len(accounts) == 1
        in_account = [x for x in db.month_entries(NOV) if x.account_id == accounts[0].id]
        assert sorted(x.description for x in in_account) == ["groceries", "uber"]


def test_edit_after_importing_beats_what_came_in(pc, phone, tmp_path):
    """The phone's clock is behind, but the edit made after importing counts."""
    phone.now_ms = Clock(10)
    id_pc = _add(pc, "bakery")
    pc.rename(id_pc, "new bakery")
    _exchange(pc, phone, tmp_path)
    on_phone = phone.month_entries(NOV)[0]
    phone.rename(on_phone.id, "corner bakery")
    _exchange(phone, pc, tmp_path)
    assert _descriptions(pc) == ["corner bakery"]


def test_series_does_not_duplicate_and_deleted_month_does_not_come_back(pc, phone, tmp_path):
    account = pc.create_account("nubank", "#8a2be2")
    rent = pc.create_category("rent", recurring=True)
    pc.insert_entries(
        [
            NewEntry(
                dt.date(2026, 11, 5),
                "rent",
                100000,
                Kind.EXPENSE,
                account.id,
                rent.id,
                recurrence_group=pc.new_installment_group(),
            )
        ]
    )
    _exchange(pc, phone, tmp_path)
    code = exchange.check_code(pc)

    # Each one browses to a different month: they generate the same records, and the code
    # does not change.
    pc.extend_recurrences(Month(2027, 1))
    phone.extend_recurrences(Month(2027, 3))
    assert exchange.check_code(pc) == code == exchange.check_code(phone)

    # The phone deletes December ("only this") and edits January; the PC does not know.
    december = phone.month_entries(Month(2026, 12))[0]
    phone.delete(december.id, Scope.ONLY_THIS)
    january = phone.month_entries(Month(2027, 1))[0]
    phone.edit(
        january.id,
        NewEntry(
            january.date, "rent", 110000, Kind.EXPENSE, january.account_id, january.category_id
        ),
        Scope.ONLY_THIS,
    )
    assert exchange.check_code(pc) != exchange.check_code(phone)

    _exchange(phone, pc, tmp_path)
    _exchange(pc, phone, tmp_path)
    for db in (pc, phone):
        db.extend_recurrences(Month(2027, 4))  # browsing again brings nothing back
        assert db.month_entries(Month(2026, 12)) == []
        assert [x.amount for x in db.month_entries(Month(2027, 1))] == [110000]
        for month in (Month(2027, 2), Month(2027, 3), Month(2027, 4)):
            assert [x.amount for x in db.month_entries(month)] == [100000]
    assert exchange.check_code(pc) == exchange.check_code(phone)


def test_series_edited_on_one_side_applies_to_months_the_other_will_still_generate(
    pc, phone, tmp_path
):
    account = pc.create_account("nubank", "#8a2be2")
    power = pc.create_category("power", recurring=True)
    first = pc.insert_entries(
        [
            NewEntry(
                dt.date(2026, 11, 31 - 1),
                "power",
                20000,
                Kind.EXPENSE,
                account.id,
                power.id,
                recurrence_group=pc.new_installment_group(),
            )
        ]
    )[0]
    _exchange(pc, phone, tmp_path)
    phone.extend_recurrences(Month(2026, 12))  # generates December with the old amount
    item = pc.entry(first)
    pc.edit(
        first,
        NewEntry(item.date, "power", 25000, Kind.EXPENSE, account.id, power.id),
        Scope.UPCOMING,
    )
    pc.extend_recurrences(Month(2026, 12))  # generates December with the new amount

    _exchange(pc, phone, tmp_path)
    _exchange(phone, pc, tmp_path)
    for db in (pc, phone):
        db.extend_recurrences(Month(2027, 1))
        for month in (NOV, Month(2026, 12), Month(2027, 1)):
            assert [x.amount for x in db.month_entries(month)] == [25000]
    assert exchange.read_state(pc) == exchange.read_state(phone)


def test_import_keeps_a_copy_first_and_a_bad_file_changes_nothing(tmp_path, phone):
    folder = tmp_path / "pc"
    pc = Database.open(folder / "money.sqlite")
    _add(pc, "bakery")
    before = exchange.read_state(pc)

    bad = tmp_path / "bad.json"
    bad.write_text('{"app": "kotsu", "format": 2, "accounts": "no"}', encoding="utf-8")
    with pytest.raises(merge.ExchangeError):
        exchange.import_file(pc, bad)
    with pytest.raises(merge.ExchangeError):
        exchange.import_file(pc, tmp_path / "does-not-exist.json")
    assert exchange.read_state(pc) == before
    assert not (folder / "backups").exists()

    _add(phone, "uber")
    summary = _exchange(phone, pc, tmp_path)
    assert summary.added == 1
    copy = folder / "backups" / "money.before-import.sqlite"
    assert copy.exists()
    assert lock.conflicts(folder, "money.sqlite") == []  # the copy does not look like a conflict
    previous = Database.open(copy)
    assert _descriptions(previous) == ["bakery"]
    previous.close()
    pc.close()


def test_a_format_1_file_from_an_older_version_is_imported(pc, phone, tmp_path):
    """Files exported by the Portuguese versions (format 1) still import."""
    _add(phone, "uber", category="transport")
    state = exchange.read_state(phone)
    v1 = {"app": "kotsu", "formato": 1, "replica": phone.replica}
    v1["contas"] = [
        {"uid": a["uid"], "nome": a["name"], "cor": a["color"], "alterado_em": a["changed_at"]}
        for a in state["accounts"]
    ]
    v1["categorias"] = [
        {
            "uid": c["uid"],
            "nome": c["name"],
            "recorrente": c["recurring"],
            "alterado_em": c["changed_at"],
        }
        for c in state["categories"]
    ]
    v1["recorrencias"] = []
    v1["lancamentos"] = [
        {
            "uid": e["uid"],
            "data": e["date"],
            "descricao": e["description"],
            "valor": e["amount"],
            "tipo": "despesa",
            "conta": e["account"],
            "categoria": e["category"],
            "parcela": None,
            "recorrencia": None,
            "gerado": False,
            "alterado_em": e["changed_at"],
        }
        for e in state["entries"]
    ]
    v1["lapides"] = [{"uid": "gone", "excluido_em": merge.ZERO_STAMP}]
    file = tmp_path / "old.json"
    file.write_text(json.dumps(v1, ensure_ascii=False), encoding="utf-8")

    assert exchange.import_file(pc, file).added == 1
    assert exchange.check_code(pc) != exchange.check_code(phone)  # the tombstone came along
    (entry,) = pc.month_entries(NOV)
    assert (entry.description, entry.kind) == ("uber", Kind.EXPENSE)
    assert [c.name for c in pc.list_categories()] == ["transport"]


def test_exported_file_is_readable_valid_json(pc, tmp_path):
    _add(pc, "pão de ló", category="alimentação")
    file = tmp_path / "sub" / "kotsu-pc.json"
    code = exchange.export(pc, file, dt.datetime(2026, 11, 11, 10, 0, 0))
    data = json.loads(file.read_text(encoding="utf-8"))
    assert data["app"] == "kotsu" and data["format"] == merge.FORMAT
    assert data["replica"] == pc.replica
    assert data["exported_at"] == "2026-11-11T10:00:00"
    assert data["check_code"] == code == merge.check_code(data)
    assert "alimentação" in file.read_text(encoding="utf-8")  # accents are not escaped
    assert list(file.parent.iterdir()) == [file]  # no temporary file left
    merge.validate(data)


def test_compare_lists_what_is_missing_on_each_side(pc, phone, tmp_path):
    bakery = _add(pc, "bakery")
    _exchange(pc, phone, tmp_path)
    _add(pc, "groceries")
    _add(phone, "uber")
    pc.rename(bakery, "corner bakery")
    file = tmp_path / "phone.json"
    exchange.export(phone, file)
    differences = exchange.compare(pc, file)
    assert not differences.equal
    assert [x["description"] for x in differences.only_here] == ["groceries"]
    assert [x["description"] for x in differences.only_there] == ["uber"]
    assert [(a["description"], b["description"]) for a, b in differences.different] == [
        ("corner bakery", "bakery")
    ]
    here = exchange.read_state(pc)
    assert merge.describe(differences.only_here[0], here) == "08/11/2026 -10,00 groceries @nubank"


# --- command line and screen ----------------------------------------------------------


def test_export_import_verify_commands(tmp_path, capsys):
    pc, phone = tmp_path / "pc", tmp_path / "phone"
    db = Database.open(pc / "money.sqlite")
    _add(db, "bakery")
    db.close()
    file = tmp_path / "pc.json"

    assert main(["--data", str(pc), "--export", str(file)]) == 0
    code = json.loads(file.read_text(encoding="utf-8"))["check_code"]
    assert code in capsys.readouterr().out

    assert main(["--data", str(phone), "--import", str(file)]) == 0
    out = capsys.readouterr().out
    assert "1 added, 0 changed, 0 removed" in out and code in out

    assert main(["--data", str(phone), "--verify"]) == 0
    assert code in capsys.readouterr().out
    assert main(["--data", str(phone), "--verify", str(file)]) == 0
    assert "Equal" in capsys.readouterr().out
    assert main(["--dados", str(phone), "--conferir", str(file)]) == 0  # old flags
    assert "Equal" in capsys.readouterr().out

    db = Database.open(phone / "money.sqlite")
    _add(db, "uber")
    db.close()
    assert main(["--data", str(phone), "--verify", str(file)]) == 2
    out = capsys.readouterr().out
    assert "Only here (1):" in out and "uber" in out

    assert main(["--data", str(pc), "--import", str(tmp_path / "nothing.json")]) == 1
    assert "That did not work" in capsys.readouterr().err
    assert not (pc / lock.LOCK_NAME).exists()  # the lock is released on exit


def test_exchange_commands_respect_the_lock(tmp_path, capsys):
    folder = tmp_path / "pc"
    folder.mkdir()
    (folder / lock.LOCK_NAME).write_text(
        json.dumps({"machine": "NOTEBOOK", "pid": 1, "since": "10/11/2026 22:00"}),
        encoding="utf-8",
    )
    assert main(["--data", str(folder), "--export", str(tmp_path / "x.json")]) == 1
    assert "NOTEBOOK" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


async def test_key_v_shows_the_check_code(db):
    _add(db, "bakery")
    app = KotsuApp(db, today=dt.date(2026, 11, 11))
    async with app.run_test() as pilot:
        await pilot.press("v")
        await pilot.pause()
        notices = [notice.message for notice in app._notifications]
    assert notices == [f"Check code: {exchange.check_code(db)}"]
