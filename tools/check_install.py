"""Installs via pipx and checks the package outside the checkout, with temporary data.

Requires `python -m pip install pipx`. Uses the network only to install dependencies;
it is not part of the unit tests and does not touch real data.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], folder: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        cwd=folder,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kotsu-pipx-") as name:
        folder = Path(name)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("KOTSU_DATA", None)
        env.pop("MONEY_CLI_DADOS", None)
        env.update(
            PIPX_HOME=str(folder / "pipx"),
            PIPX_BIN_DIR=str(folder / "bin"),
            PIPX_MAN_DIR=str(folder / "man"),
            PIPX_DEFAULT_PYTHON=sys.executable,
            PIPX_LOG_DIR=str(folder / "logs"),
            PIPX_CACHE_DIR=str(folder / "cache"),
            UV_CACHE_DIR=str(folder / "uv-cache"),
            PIP_CACHE_DIR=str(folder / "pip-cache"),
            PYTHONUTF8="1",
        )
        run([sys.executable, "-m", "pipx", "install", str(ROOT)], folder, env)
        kotsu = folder / "bin" / ("kotsu.exe" if sys.platform == "win32" else "kotsu")
        # The old alias is still installed.
        assert (folder / "bin" / ("money.exe" if sys.platform == "win32" else "money")).exists()
        py = (
            folder
            / "pipx"
            / "venvs"
            / "kotsu-cli"
            / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        )
        assert "kotsu" in run([str(kotsu), "--version"], folder, env)
        assert "--data" in run([str(kotsu), "--help"], folder, env)
        data = folder / "data"
        # Python from pipx's own venv, without PYTHONPATH or the checkout's cwd.
        code = """
import asyncio
import datetime as dt
import sys
from pathlib import Path
import kotsu
from kotsu.storage import migrations
from kotsu.storage.database import Database
from kotsu.ui.app import KotsuApp
from kotsu.domain.models import NewEntry, Kind
from textual.widgets import DataTable
assert Path(sys.argv[2]).resolve() not in Path(kotsu.__file__).resolve().parents
async def check():
    database = Database.open(Path(sys.argv[1]) / 'money.sqlite')
    try:
        assert database.version == len(migrations.load()) >= 4
        account = database.create_account('Sample account', '#8a2be2')
        database.insert_entries([
            NewEntry(dt.date(2026, 11, 8), 'Coffee', 8990, Kind.EXPENSE, account.id)
        ])
        app = KotsuApp(database, today=dt.date(2026, 11, 8))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one('#entries', DataTable).row_count == 1
            await pilot.press('b')
            await pilot.pause()
            await pilot.press('q')
        assert list((Path(sys.argv[1]) / 'backups').glob('money.*.sqlite'))
    finally:
        database.close()
asyncio.run(check())
"""
        run([str(py), "-c", code, str(data), str(ROOT)], folder, env)
        print("pipx: install, CLI, migrations, UI and backup ok outside the checkout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
