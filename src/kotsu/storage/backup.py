"""Manual SQLite backup: each request publishes a new full copy and keeps the latest 5."""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import tempfile
from pathlib import Path

KEEP = 5


def manual_backup(
    connection: sqlite3.Connection,
    path: Path,
    now: dt.datetime,
    folder: Path | None = None,
) -> Path:
    from kotsu.storage.database import copy_database

    folder = folder or path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{path.stem}.{now:%Y-%m-%d-%H%M%S}"
    fd, name = tempfile.mkstemp(prefix=".backup-", suffix=".tmp", dir=folder)
    os.close(fd)  # Windows: close before SQLite opens the same file.
    temporary = Path(name)
    try:
        copy_database(connection, temporary)
        with temporary.open("r+b") as file:
            os.fsync(file.fileno())
        # Same second: a suffix larger than that of any existing copy, so that name order
        # stays creation order after pruning.
        used = [_number(p.name, base) for p in folder.glob(f"{base}*.sqlite")]
        for attempt in range(max([0, *used]) + 1, max([0, *used]) + 1000):
            target = folder / (f"{base}.sqlite" if attempt == 1 else f"{base}-{attempt}.sqlite")
            try:
                # Atomic publish without overwriting an existing copy (NTFS and Linux).
                os.link(temporary, target)
                break
            except FileExistsError:
                continue
        else:
            raise OSError("could not pick a free name for the backup")
    finally:
        temporary.unlink(missing_ok=True)
    _prune(folder, path.stem)
    return target


def _number(name: str, base: str) -> int:
    rest = name[len(base) : -len(".sqlite")]
    return int(rest[1:]) if re.fullmatch(r"-\d+", rest) else 1 if rest == "" else 0


def _prune(folder: Path, stem: str) -> None:
    """Only after publishing: keeps the `KEEP` most recent.

    Only looks at copies named by this module (`money.YYYY-MM-DD-HHMMSS[-N].sqlite`);
    pre-migration copies, backups in other formats and other files are never touched.
    """
    pattern = re.compile(re.escape(stem) + r"\.(\d{4}-\d{2}-\d{2}-\d{6})(?:-(\d+))?\.sqlite")
    copies = []
    for file in folder.iterdir():
        found = pattern.fullmatch(file.name)
        if found and file.is_file():
            copies.append(((found[1], int(found[2] or 1)), file))
    for _, old in sorted(copies, reverse=True)[KEEP:]:
        old.unlink(missing_ok=True)
