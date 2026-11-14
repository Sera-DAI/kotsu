import datetime as dt
import subprocess
import sys
import time

import pytest
from textual.widgets import DataTable, Static

from kotsu.domain.models import Installment, Kind, NewEntry
from kotsu.ui.app import KotsuApp

TODAY = dt.date(2026, 11, 8)


async def test_opens_empty_in_under_1s(db):
    start = time.perf_counter()
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.pause()
        elapsed = time.perf_counter() - start
        assert app.query_one("#empty", Static).display
        assert not app.query_one("#entries", DataTable).display
        top = str(app.query_one("#top", Static).render())
        assert "November 2026" in top and "0,00" in top
        await pilot.press("q")
    assert elapsed < 1.0, f"opened in {elapsed:.2f} s"


async def test_switches_month_and_shows_entries(db):
    nubank = db.create_account("Nubank", "#8a2be2")
    group = db.new_installment_group()
    db.insert_entries(
        [
            NewEntry(
                dt.date(2026, 10, 2),
                "fridge",
                12000,
                Kind.EXPENSE,
                nubank.id,
                installment=Installment(group, 3, 10),
            ),
        ]
    )
    app = KotsuApp(db, today=TODAY)
    async with app.run_test() as pilot:
        await pilot.press("left")
        table = app.query_one("#entries", DataTable)
        assert app.month.month == 10 and table.display and table.row_count == 1
        assert "fridge 3/10" in str(table.get_row_at(0)[1])
        assert "120,00" in str(app.query_one("#top", Static).render())
        await pilot.press("right", "right")
        assert app.month.month == 12 and not table.display


@pytest.mark.slow
def test_real_process_starts_fast(tmp_path):
    """Imports everything and opens the database in a new process, as the user does."""
    code = (
        "import time; t=time.perf_counter();"
        "from kotsu.ui.app import KotsuApp;"
        "from kotsu.storage.database import Database;"
        f"d=Database.open(__import__('pathlib').Path(r'{tmp_path}')/'kotsu.sqlite');"
        "print(time.perf_counter()-t)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert float(out.stdout) < 1.0
