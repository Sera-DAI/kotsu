"""Kotsu's checker, in two levels.

    python tools/check.py --quick   lint, layers and fast tests
    python tools/check.py           everything, slow tests included

Run it before every commit; the full one before every PR.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="skips the slow tests")
    args = parser.parse_args(argv)

    py = sys.executable
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
