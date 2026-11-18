"""Kotsu's checker, in two levels.

    python tools/check.py --quick   lint, layers and fast tests
    python tools/check.py           everything, slow tests included

Run it before every commit; the full one before every PR. A full run that passes on a clean,
committed HEAD stamps it for the push gate (`tools/pre_push_gate.py`).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _step(name: str, command: list[str]) -> bool:
    start = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT)
    duration = time.perf_counter() - start
    state = "ok" if result.returncode == 0 else "FAILED"
    print(f"--> {name}: {state} ({duration:.1f} s)\n", flush=True)
    return result.returncode == 0


def _stamp_head(root: Path = ROOT, expected_head: str = "") -> bool:
    """Records that the full check passed on the current, committed HEAD (read by the push gate)."""

    def git(*args: str) -> str | None:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else None

    head = git("rev-parse", "HEAD")
    stamp = git("rev-parse", "--git-path", "verify-stamp")
    if not head or not stamp:
        return False  # not a git checkout
    if expected_head and head != expected_head:
        print("not stamped: HEAD moved while the checks were running")
        return False
    status = git("status", "--porcelain")
    if status is None:
        print("not stamped: git status failed")
        return False
    if status:
        print("not stamped: the working tree has uncommitted changes")
        return False
    (root / stamp).write_text(head)
    return True


def _head(root: Path = ROOT) -> str:
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="skips the slow tests")
    args = parser.parse_args(argv)

    py = sys.executable
    head = _head()
    steps = [
        ("ruff (lint)", [py, "-m", "ruff", "check", "."]),
        ("ruff (format)", [py, "-m", "ruff", "format", "--check", "."]),
        ("layers", [py, "tools/layers.py"]),
        ("tests", [py, "-m", "pytest", *(["-m", "not slow"] if args.quick else [])]),
    ]
    failures = [name for name, command in steps if not _step(name, command)]
    level = "quick" if args.quick else "full"
    if failures:
        print(f"Checker ({level}): FAILED in {', '.join(failures)}")
        return 1
    print(f"Checker ({level}): all ok")
    if not args.quick and head:
        _stamp_head(expected_head=head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
