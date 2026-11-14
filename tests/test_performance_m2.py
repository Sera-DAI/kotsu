"""M2 criterion 12: with 50 thousand entries, switching months takes less than 150 ms."""

import datetime as dt
import random
import statistics
import time

import pytest

from kotsu.domain.filter import Filter
from kotsu.domain.models import Installment, Kind, NewEntry
from kotsu.domain.month import Month
from kotsu.storage.database import Database
from kotsu.ui.app import KotsuApp

LIMIT_MS = 150
TODAY = dt.date(2026, 11, 8)


def _sample_database(path, count=50_000, months=60) -> Database:
    """~830 entries per month over 5 years, 6 accounts, 12 categories, 1 in 10 in installments."""
    rng = random.Random(42)
    db = Database.open(path)
    accounts = [db.create_account(f"account{i}", "#8a2be2").id for i in range(6)]
    categories = [db.create_category(f"cat{i}").id for i in range(12)]
    start = Month.of(TODAY).add(-months + 1)
    new = []
    for i in range(count):
        month = start.add(rng.randrange(months))
        installment = None
        if i % 10 == 0:
            installment = Installment(f"g{i}", rng.randint(1, 10), 10)
        new.append(
            NewEntry(
                dt.date(month.year, month.month, rng.randint(1, 28)),
                f"store {i}",
                rng.randint(100, 500_000),
                Kind.INCOME if i % 15 == 0 else Kind.EXPENSE,
                rng.choice(accounts),
                rng.choice([None, *categories]),
                installment,
            )
        )
    db.insert_entries(new)
    return db


@pytest.mark.slow
async def test_switching_months_with_50_thousand_entries(tmp_path):
    """Measures two things on each month switch, with and without a filter:

    - queries + building the list (`action_month`): the worst case must stay under the limit;
    - that plus redrawing the screen (`pause`): the median stays under the limit. Only the
      median, because the test pilot's pause alone sometimes goes over 100 ms.
    """
    db = _sample_database(tmp_path / "kotsu.sqlite")
    try:
        app = KotsuApp(db, today=TODAY)
        results = {}
        async with app.run_test() as pilot:
            for name, filter in [("no filter", Filter()), ("with filter", Filter(account_id=1))]:
                app.filter = filter
                action, total = [], []
                for step in [-1] * 6 + [1] * 6:
                    start = time.perf_counter()
                    app.action_month(step)
                    action.append((time.perf_counter() - start) * 1000)
                    await pilot.pause()
                    total.append((time.perf_counter() - start) * 1000)
                    assert app.query_one("#entries").row_count > 0
                results[name] = (max(action), statistics.median(total))
        for name, (worst, median) in results.items():
            print(f"{name}: queries and list worst {worst:.0f} ms; with redraw {median:.0f} ms")
            assert worst < LIMIT_MS, f"{name}: switching months took {worst:.0f} ms"
            assert median < LIMIT_MS, f"{name}: with redraw it took {median:.0f} ms"
    finally:
        db.close()
