"""Numbered migrations: NNNN_name.sql files in this folder, applied in order."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

_PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def load() -> list[Migration]:
    """Reads the package's migrations and checks the numbering is 1, 2, 3... with no gaps."""
    found = []
    for item in resources.files(__package__).iterdir():
        match = _PATTERN.match(item.name)
        if match:
            found.append(
                Migration(int(match.group(1)), item.name, item.read_text(encoding="utf-8"))
            )
    found.sort(key=lambda m: m.version)
    for expected, migration in enumerate(found, start=1):
        if migration.version != expected:
            raise RuntimeError(f"migration {expected:04d} missing before {migration.name}")
    return found
