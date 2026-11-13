"""Generates the test cases shared by Kotsu on the PC (Python) and on Android (Kotlin).

    python tools/generate_vectors.py           rewrites vectors/*.json
    python tools/generate_vectors.py --check   fails if the files are out of date

Each file in `vectors/` is a list of cases: inputs and the output both implementations must
give (D39). The inputs live in this script; the outputs come from the Python domain, which
is the reference. Changed a rule? Add the case here, regenerate and review the JSON diff
before committing.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kotsu.domain import installments, merge, money, recurrence  # noqa: E402
from kotsu.domain.line import LineError, parse  # noqa: E402
from kotsu.domain.month import Month  # noqa: E402

FOLDER = ROOT / "vectors"

# --- quick line ----------------------------------------------------------------

TODAY = "2026-11-11"
LINES = [
    "89,90 groceries #food @nubank",
    "-89,90 groceries @nubank",
    "+3500 salary @itaú",
    "+3.500,00 salary @itaú 05/11",
    "120 fridge #home @nubank 10x",
    "120 fridge #home @nubank 10X 31/01/2027",
    "89.90 groceries @nubank",
    "1.234,56 trip @nubank",
    "1.234 trip @nubank",
    "1234,5 trip @nubank",
    "12 breakfast coffee @nubank yesterday",
    "12 coffee @nubank today",
    "12 coffee @nubank ontem",
    "12 coffee @nubank HOJE",
    "12 coffee @nubank 1/2",
    "12 coffee @nubank 15/10/25",
    "12 coffee @nubank 29/02/2028",
    "12 @nubank",
    "12 coffee",
    "12    coffee   with   spaces   @nubank",
    "12 pix 2x1 @nubank",
    "12 note 10/2026 @nubank",
    "12 a #b @c #d",
    "12 a @b @c",
    "12 a @b 2x 3x",
    "12 a @b 1x",
    "12 a @b 121x",
    "12 a @b 120x",
    "12 a @b 01/01 02/01",
    "12 a @b 31/02",
    "12 a #",
    "12 a @",
    "0 nothing @b",
    "0,00 nothing @b",
    "abc groceries @b",
    "12,345 groceries @b",
    "1.23.456 groceries @b",
    "1,2,3 groceries @b",
    "+ salary @b",
    "",
    "   ",
    "R$12 groceries @b",
    "12 GROCERIES #Alimentação @NuBank",
]


def _lines() -> list[dict]:
    cases = []
    for line in LINES:
        case: dict = {"line": line, "today": TODAY}
        try:
            parsed = parse(line, dt.date.fromisoformat(TODAY))
        except LineError as error:
            case["error"] = str(error)
        else:
            case["expected"] = {
                "amount": parsed.amount,
                "kind": parsed.kind.value,
                "description": parsed.description,
                "date": parsed.date.isoformat(),
                "category": parsed.category,
                "account": parsed.account,
                "installments": parsed.installments,
                "has_date": parsed.has_date,
            }
        cases.append(case)
    return cases


# --- dates and money -------------------------------------------------------------


def _dates() -> dict:
    firsts = ["2026-01-31", "2026-11-11", "2027-12-15", "2028-01-29", "2026-08-30"]
    days = [1, 15, 28, 29, 30, 31]
    months = [(2026, 2), (2028, 2), (2026, 4), (2026, 12), (2100, 2)]
    return {
        "installments": [
            {
                "first": first,
                "index": index,
                "date": installments.installment_date(
                    dt.date.fromisoformat(first), index
                ).isoformat(),
            }
            for first in firsts
            for index in (0, 1, 2, 11, 12, 25)
        ],
        "recurrence": [
            {
                "day": day,
                "year": year,
                "month": month,
                "date": recurrence.date_in_month(day, Month(year, month)).isoformat(),
            }
            for day in days
            for year, month in months
        ],
        "month_uid": [
            {
                "group": "series1",
                "year": 2026,
                "month": 3,
                "uid": merge.month_uid("series1", 2026, 3),
            },
            {"group": "s", "year": 2027, "month": 12, "uid": merge.month_uid("s", 2027, 12)},
        ],
    }


def _money() -> list[dict]:
    values = [0, 1, 9, 10, 99, 100, 1250, 99999, 100000, 123456, 100000000, 123456789012, -8990]
    return [{"cents": v, "text": money.format_cents(v)} for v in values]


# --- stamps ----------------------------------------------------------------------


def _stamps() -> list[dict]:
    inputs = [
        (1762850000000, merge.ZERO_STAMP, "ab12cd34"),
        (1762850000000, "1762850000000-0000-ab12cd34", "ab12cd34"),
        (1762850000000, "1762850000000-0007-ffffffff", "ab12cd34"),
        (1762850000000, "1762850000000-9999-ab12cd34", "ab12cd34"),
        (1762849999999, "1762850000000-0003-ab12cd34", "ab12cd34"),  # clock went back
        (1762850000001, "1762850000000-0003-ab12cd34", "00000000"),
        (5, merge.ZERO_STAMP, "00000001"),
    ]
    return [
        {
            "now_ms": ms,
            "last": last,
            "replica": replica,
            "stamp": merge.stamp(ms, last, replica),
        }
        for ms, last, replica in inputs
    ]


# --- merging ---------------------------------------------------------------------


def _c(ms: int, replica: str = "aaaaaaaa", counter: int = 0) -> str:
    """Short stamp for the cases: `_c(5)` = 5 ms on replica A."""
    return f"{ms:013d}-{counter:04d}-{replica}"


A, B = "aaaaaaaa", "bbbbbbbb"


def account(uid: str, name: str, at: str, color: str = "#ff85bd") -> dict:
    return {"uid": uid, "name": name, "color": color, "changed_at": at}


def category(uid: str, name: str, at: str, recurring: bool = False) -> dict:
    return {"uid": uid, "name": name, "recurring": recurring, "changed_at": at}


def entry(uid: str, at: str, **others) -> dict:
    return {
        "uid": uid,
        "date": "2026-11-08",
        "description": "bakery",
        "amount": 1250,
        "kind": "expense",
        "account": "c-nu",
        "category": None,
        "installment": None,
        "recurrence": None,
        "generated": False,
        "changed_at": at,
        **others,
    }


def series(group: str, at: str, **others) -> dict:
    return {
        "group": group,
        "day": 5,
        "description": "rent",
        "amount": 100000,
        "kind": "expense",
        "account": "c-nu",
        "category": "g-rent",
        "generated_until": "2026-11-01",
        "ended": False,
        "changed_at": at,
        **others,
    }


def tombstone(uid: str, at: str) -> dict:
    return {"uid": uid, "deleted_at": at}


def state(**sections) -> dict:
    base = {"app": "kotsu", "format": merge.FORMAT}
    return {**base, **{section: sections.get(section, []) for section in merge.SECTIONS}}


NU = account("c-nu", "nubank", _c(1))
RENT = category("g-rent", "rent", _c(1), recurring=True)

MERGE_CASES: list[tuple[str, dict, dict]] = [
    ("two empty states", state(), state()),
    (
        "entry created on each side shows on both",
        state(accounts=[NU], entries=[entry("l-1", _c(10))]),
        state(
            accounts=[NU],
            entries=[entry("l-2", _c(11, B), description="uber", amount=2000)],
        ),
    ),
    (
        "same entry edited on both sides: the larger stamp wins, whole",
        state(
            accounts=[NU],
            entries=[entry("l-1", _c(20), description="joe's bakery", amount=1250)],
        ),
        state(accounts=[NU], entries=[entry("l-1", _c(30, B), description="bakery", amount=1500)]),
    ),
    (
        "same millisecond: the counter breaks the tie, then the replica",
        state(accounts=[NU], entries=[entry("l-1", _c(20, A, 2), description="a")]),
        state(accounts=[NU], entries=[entry("l-1", _c(20, B, 1), description="b")]),
    ),
    (
        "exact same stamp: the replica breaks the tie",
        state(accounts=[NU], entries=[entry("l-1", _c(20, A), description="a")]),
        state(accounts=[NU], entries=[entry("l-1", _c(20, B), description="b")]),
    ),
    (
        "deleted on one side after the other's last edit: removed",
        state(accounts=[NU], tombstones=[tombstone("l-1", _c(40))]),
        state(accounts=[NU], entries=[entry("l-1", _c(30, B))]),
    ),
    (
        "edited on one side after deleted on the other: comes back",
        state(accounts=[NU], tombstones=[tombstone("l-1", _c(40))]),
        state(accounts=[NU], entries=[entry("l-1", _c(50, B), description="came back")]),
    ),
    (
        "tombstones on both sides: the newest stays",
        state(tombstones=[tombstone("l-1", _c(40)), tombstone("l-2", _c(41))]),
        state(tombstones=[tombstone("l-1", _c(45, B))]),
    ),
    (
        "same account created on both sides: one remains, smallest uid and newest content",
        state(
            accounts=[account("c-zz", "Itaú", _c(5), color="#ff7a00")],
            entries=[entry("l-1", _c(10), account="c-zz")],
        ),
        state(
            accounts=[account("c-aa", "ITAÚ", _c(7, B), color="#0000ff")],
            entries=[entry("l-2", _c(11, B), account="c-aa")],
        ),
    ),
    (
        "same category created on both sides with another spelling",
        state(
            accounts=[NU],
            categories=[category("g-2", "Home", _c(5))],
            entries=[entry("l-1", _c(10), category="g-2")],
        ),
        state(
            accounts=[NU],
            categories=[category("g-1", "home", _c(3, B)), category("g-9", "leisure", _c(4, B))],
            entries=[entry("l-2", _c(11, B), category="g-1")],
        ),
    ),
    (
        "category marked as every month on one side",
        state(categories=[category("g-1", "power", _c(5), recurring=False)]),
        state(categories=[category("g-1", "power", _c(9, B), recurring=True)]),
    ),
    (
        "installment purchase made on one side comes in whole",
        state(accounts=[NU]),
        state(
            accounts=[NU],
            entries=[
                entry(
                    f"l-p{n}",
                    _c(10, B),
                    date=f"2026-{10 + n}-10",
                    description="fridge",
                    amount=12000,
                    installment={"group": "p-1", "number": n, "total": 2},
                )
                for n in (1, 2)
            ],
        ),
    ),
    (
        "series: both sides generated the same month; one generated further",
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2026-12-01")],
            entries=[
                entry(
                    "l-1",
                    _c(10),
                    date="2026-11-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                ),
                entry(
                    "s-1-2026-12",
                    _c(10),
                    date="2026-12-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                    generated=True,
                ),
            ],
        ),
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2027-01-01")],
            entries=[
                entry(
                    "l-1",
                    _c(10),
                    date="2026-11-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                ),
                entry(
                    "s-1-2026-12",
                    _c(10),
                    date="2026-12-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                    generated=True,
                ),
                entry(
                    "s-1-2027-01",
                    _c(10),
                    date="2027-01-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                    generated=True,
                ),
            ],
        ),
    ),
    (
        "series: month generated on one side and deleted (only this) on the other stays deleted",
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2026-12-01")],
            tombstones=[tombstone("s-1-2026-12", _c(50))],
        ),
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2026-12-01")],
            entries=[
                entry(
                    "s-1-2026-12",
                    _c(10),
                    date="2026-12-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                    generated=True,
                ),
            ],
        ),
    ),
    (
        "series: month generated on one side and edited on the other keeps the edit",
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2026-12-01")],
            entries=[
                entry(
                    "s-1-2026-12",
                    _c(10),
                    date="2026-12-05",
                    description="rent",
                    amount=100000,
                    category="g-rent",
                    recurrence="s-1",
                    generated=True,
                ),
            ],
        ),
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2026-12-01")],
            entries=[
                entry(
                    "s-1-2026-12",
                    _c(60, B),
                    date="2026-12-05",
                    description="rent",
                    amount=110000,
                    category="g-rent",
                    recurrence="s-1",
                    generated=False,
                ),
            ],
        ),
    ),
    (
        "series: ended on one side, older template on the other",
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(70), generated_until="2026-12-01", ended=True)],
        ),
        state(
            accounts=[NU],
            categories=[RENT],
            recurrences=[series("s-1", _c(10), generated_until="2027-03-01")],
        ),
    ),
    (
        "series and entry follow the unified account",
        state(
            accounts=[account("c-nu", "nubank", _c(1))],
            categories=[RENT],
            recurrences=[series("s-1", _c(10))],
        ),
        state(
            accounts=[account("c-b", "Nubank", _c(2, B))],
            categories=[category("g-b", "Rent", _c(2, B), recurring=True)],
            recurrences=[series("s-2", _c(12, B), account="c-b", category="g-b", day=31)],
            entries=[entry("l-9", _c(12, B), account="c-b", category="g-b", recurrence="s-2")],
        ),
    ),
    (
        "description with separators and accents goes into the code the same way",
        state(accounts=[NU], entries=[entry("l-1", _c(10), description="pão\\de\x1fló\nção")]),
        state(accounts=[NU], entries=[entry("l-1", _c(10), description="pão\\de\x1fló\nção")]),
    ),
]


def _merges() -> list[dict]:
    cases = []
    for name, a, b in MERGE_CASES:
        merge.validate(a)
        merge.validate(b)
        expected = merge.merge(a, b)
        cases.append(
            {
                "name": name,
                "a": a,
                "b": b,
                "expected": expected,
                "code_a": merge.check_code(a),
                "code_b": merge.check_code(b),
                "expected_code": merge.check_code(expected),
                "expected_canonical_form": merge.canonical_form(expected),
            }
        )
    return cases


# --- invalid files -----------------------------------------------------------------


def _invalid() -> list[dict]:
    good = state(accounts=[NU], categories=[RENT], entries=[entry("l-1", _c(10))])
    inputs: list[tuple[str, object]] = [
        ("not an object", []),
        ("another app", {**good, "app": "other"}),
        ("no format", {k: v for k, v in good.items() if k != "format"}),
        ("newer format", {**good, "format": merge.FORMAT + 1}),
        ("a section is missing", {k: v for k, v in good.items() if k != "tombstones"}),
        ("zero amount", {**good, "entries": [entry("l-1", _c(10), amount=0)]}),
        ("amount with decimals", {**good, "entries": [entry("l-1", _c(10), amount=12.5)]}),
        ("unknown kind", {**good, "entries": [entry("l-1", _c(10), kind="other")]}),
        ("impossible date", {**good, "entries": [entry("l-1", _c(10), date="2026-02-30")]}),
        ("unknown account", {**good, "entries": [entry("l-1", _c(10), account="c-x")]}),
        ("unknown category", {**good, "entries": [entry("l-1", _c(10), category="g-x")]}),
        ("unknown series", {**good, "entries": [entry("l-1", _c(10), recurrence="s-x")]}),
        ("duplicate entry", {**good, "entries": [entry("l-1", _c(10)), entry("l-1", _c(11))]}),
        ("crooked stamp", {**good, "entries": [entry("l-1", "yesterday")]}),
        (
            "installment beyond the total",
            {
                **good,
                "entries": [
                    entry("l-1", _c(10), installment={"group": "p", "number": 3, "total": 2})
                ],
            },
        ),
        (
            "accounts with the same name",
            {**good, "accounts": [NU, account("c-2", "NUBANK", _c(2))]},
        ),
        ("entry without a field", {**good, "entries": [{"uid": "l-1"}]}),
    ]
    cases = []
    for name, value in inputs:
        try:
            merge.validate(value)
        except merge.ExchangeError as error:
            cases.append({"name": name, "file": value, "error": str(error)})
        else:
            raise AssertionError(f"invalid case passed validation: {name}")
    return cases


# --- files -------------------------------------------------------------------------


def generate() -> dict[str, object]:
    """Content of each file in `vectors/`, by name."""
    return {
        "line.json": _lines(),
        "dates.json": _dates(),
        "money.json": _money(),
        "stamp.json": _stamps(),
        "merge.json": _merges(),
        "invalid.json": _invalid(),
    }


def _text(content: object) -> str:
    return json.dumps(content, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def out_of_date() -> list[str]:
    """Names of the files in `vectors/` that do not match what this script generates."""
    wrong = []
    for name, content in generate().items():
        try:
            on_disk = json.loads((FOLDER / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            wrong.append(name)
            continue
        if on_disk != json.loads(_text(content)):
            wrong.append(name)
    return wrong


def main(argv: list[str]) -> int:
    if "--check" in argv:
        wrong = out_of_date()
        for name in wrong:
            print(f"vectors/{name} is out of date: run python tools/generate_vectors.py")
        return 1 if wrong else 0
    FOLDER.mkdir(exist_ok=True)
    for name, content in generate().items():
        (FOLDER / name).write_text(_text(content), encoding="utf-8", newline="\n")
        print(f"vectors/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
