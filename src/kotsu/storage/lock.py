"""Usage lock (D38): avoids opening the same database on two computers at once.

With the data folder on a sync service (Google Drive), two computers open together produce
"conflicted copies" and lose entries. While Kotsu is open there is a `kotsu.lock` next to
the database saying who is using it. The lock is a warning between computers, not a
guarantee: Drive takes a few seconds to propagate it.

Versions before the English rename wrote `kotsu.trava` with Portuguese keys; it is still
honored, so a computer that has not been updated yet is not ignored.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

LOCK_NAME = "kotsu.lock"
LEGACY_LOCK_NAME = "kotsu.trava"


class DatabaseInUse(Exception):
    """Another Kotsu (or another computer) has the database open."""

    def __init__(self, machine: str, since: str, same_machine: bool) -> None:
        self.machine, self.since, self.same_machine = machine, since, same_machine
        where = "on this computer" if same_machine else f"on computer {machine}"
        super().__init__(f"Kotsu is already open {where} (since {since}).")


@dataclass
class Lock:
    path: Path

    def release(self) -> None:
        """Removes the lock, only if it still belongs to this process."""
        owner = _read(self.path)
        if owner.get("pid") == os.getpid() and owner.get("machine") == _machine():
            self.path.unlink(missing_ok=True)


def acquire(folder: Path, since: str, force: bool = False) -> Lock:
    """Creates the lock or raises `DatabaseInUse`. `force` takes over another owner's lock."""
    path = folder / LOCK_NAME
    legacy = folder / LEGACY_LOCK_NAME
    folder.mkdir(parents=True, exist_ok=True)
    for candidate in (path, legacy):
        owner = _read(candidate)
        if owner and not force:
            same = owner.get("machine") == _machine()
            # On the same machine, a lock from a process that already died (power cut) is
            # discarded.
            if not (same and not _alive(int(owner.get("pid", 0)))):
                raise DatabaseInUse(
                    str(owner.get("machine", "?")), str(owner.get("since", "?")), same
                )
    content = json.dumps({"machine": _machine(), "pid": os.getpid(), "since": since})
    path.unlink(missing_ok=True)
    legacy.unlink(missing_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:  # two Kotsu at the same moment: the later one loses
        owner = _read(path)
        raise DatabaseInUse(
            str(owner.get("machine", "?")),
            str(owner.get("since", "?")),
            owner.get("machine") == _machine(),
        ) from None
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(content)
    return Lock(path)


def conflicts(folder: Path, database_name: str) -> list[Path]:
    """Copies of the database that Drive creates when it sees two edits (e.g. `kotsu (1).sqlite`).

    Ignores the database, backups and pre-migration copies (`kotsu.before-v4.sqlite`, or
    `kotsu.antes-v2.sqlite` from older versions).
    """
    stem = Path(database_name).stem
    pattern = re.compile(re.escape(stem) + r".+\.sqlite", re.IGNORECASE)
    before = re.compile(re.escape(stem) + r"\.(before|antes)-v\d+\.sqlite", re.IGNORECASE)
    try:
        items = sorted(folder.iterdir())
    except OSError:
        return []
    return [
        p
        for p in items
        if p.is_file() and pattern.fullmatch(p.name) and not before.fullmatch(p.name)
    ]


def _machine() -> str:
    return socket.gethostname()


_LEGACY_KEYS = {"maquina": "machine", "desde": "since"}


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # The lock exists but is unreadable (still syncing): treat it as of an unknown owner.
        return {"machine": "?", "pid": 0, "since": "?"} if path.exists() else {}
    if not isinstance(data, dict):
        return {}
    return {_LEGACY_KEYS.get(k, k): v for k, v in data.items()}


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":  # os.kill(pid, 0) KILLS the process on Windows
        import ctypes

        kernel = ctypes.windll.kernel32
        process = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not process:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(process, ctypes.byref(code))) and (
                code.value == 259  # STILL_ACTIVE
            )
        finally:
            kernel.CloseHandle(process)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
