"""Usage lock (D38): avoids opening the same database on two computers at once.

With the data folder on a sync service (Google Drive), two computers open together produce
"conflicted copies" and lose entries. While Kotsu is open there is a `kotsu.lock` next to
the database saying who is using it. The lock is a warning between computers, not a
guarantee: Drive takes a few seconds to propagate it.

While Kotsu runs it refreshes a heartbeat (`beat`, Unix time) in the lock every minute. A
computer that shut down with Kotsu open stops beating, so after `STALE_AFTER` seconds its
lock is considered abandoned and the other computer takes over by itself. Locks without a
heartbeat (older versions) use the file's modification time instead.

Versions before the English rename wrote `kotsu.trava` with Portuguese keys; it is still
honored, so a computer that has not been updated yet is not ignored.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

LOCK_NAME = "kotsu.lock"
LEGACY_LOCK_NAME = "kotsu.trava"
BEAT_EVERY = 60  # seconds between heartbeats
STALE_AFTER = 5 * 60  # a lock silent for this long is abandoned


class DatabaseInUse(Exception):
    """Another Kotsu (or another computer) has the database open."""

    def __init__(
        self, machine: str, since: str, same_machine: bool, silent_for: float | None = None
    ) -> None:
        self.machine, self.since, self.same_machine = machine, since, same_machine
        self.silent_for = silent_for
        where = "on this computer" if same_machine else f"on computer {machine}"
        seen = f", last seen {_ago(silent_for)}" if silent_for is not None else ""
        super().__init__(f"Kotsu is already open {where} (since {since}{seen}).")


@dataclass
class Lock:
    path: Path
    content: dict
    took_over: str | None = None  # machine whose abandoned lock was taken over, if any
    _stop: threading.Event | None = None

    def beat(self) -> None:
        """Refreshes the heartbeat, if the lock still belongs to this process."""
        owner = _read(self.path)
        if owner and not self._mine(owner):
            return  # someone forced a takeover: do not overwrite their lock
        self.content["beat"] = time.time()
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(self.content), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            pass  # Drive busy or offline: try again on the next beat

    def start_heartbeat(self) -> None:
        stop = self._stop = threading.Event()

        def run() -> None:
            while not stop.wait(BEAT_EVERY):
                self.beat()

        threading.Thread(target=run, name="kotsu-lock-heartbeat", daemon=True).start()

    def _mine(self, owner: dict) -> bool:
        return owner.get("pid") == os.getpid() and owner.get("machine") == _machine()

    def release(self) -> None:
        """Removes the lock, only if it still belongs to this process."""
        if self._stop is not None:
            self._stop.set()
        owner = _read(self.path)
        if self._mine(owner):
            self.path.unlink(missing_ok=True)


def acquire(folder: Path, since: str, force: bool = False) -> Lock:
    """Creates the lock or raises `DatabaseInUse`. `force` takes over another owner's lock.

    Abandoned locks are taken over without `force`: on the same machine when the owner
    process is dead, on another machine when its heartbeat stopped `STALE_AFTER` ago.
    """
    path = folder / LOCK_NAME
    legacy = folder / LEGACY_LOCK_NAME
    folder.mkdir(parents=True, exist_ok=True)
    took_over = None
    for candidate in (path, legacy):
        owner = _read(candidate)
        if not owner or force:
            continue
        same = owner.get("machine") == _machine()
        silent = _silent_for(candidate, owner)
        if same:
            abandoned = not _alive(_int(owner.get("pid")))
        else:
            abandoned = silent is not None and silent >= STALE_AFTER
        if not abandoned:
            raise DatabaseInUse(
                str(owner.get("machine", "?")), str(owner.get("since", "?")), same, silent
            )
        if not same:
            took_over = str(owner.get("machine", "?"))
    data = {"machine": _machine(), "pid": os.getpid(), "since": since, "beat": time.time()}
    content = json.dumps(data)
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
            _silent_for(path, owner),
        ) from None
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(content)
    return Lock(path, data, took_over)


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


def _silent_for(path: Path, owner: dict) -> float | None:
    """Seconds since the owner last showed signs of life, or None if unknown."""
    beat = owner.get("beat")
    if not isinstance(beat, (int, float)):
        try:
            beat = path.stat().st_mtime  # lock from an older version: no heartbeat
        except OSError:
            return None
    return max(0.0, time.time() - beat)


def _ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


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
