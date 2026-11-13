"""User preferences in `theme.toml`, in the data folder. An error never stops the app.

Older versions wrote `tema.toml` (key `tema`); it is read when `theme.toml` does not exist yet
and is replaced by `theme.toml` on the next save.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

FILE_NAME = "theme.toml"
LEGACY_FILE_NAME = "tema.toml"


def read_theme(folder: Path) -> str | None:
    """Name of the saved theme, or None if the file is missing, unreadable or has no `theme`."""
    for name, key in ((FILE_NAME, "theme"), (LEGACY_FILE_NAME, "tema")):
        try:
            with (folder / name).open("rb") as file:
                value = tomllib.load(file).get(key)
        except FileNotFoundError:
            continue
        except (OSError, tomllib.TOMLDecodeError):
            return None
        return value if isinstance(value, str) else None
    return None


def save_theme(folder: Path, name: str) -> bool:
    """Saves the theme via a temporary file and an atomic swap. False if it was not possible."""
    target = folder / FILE_NAME
    temporary = target.with_suffix(".toml.tmp")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        temporary.write_text(f'theme = "{name}"\n', encoding="utf-8")
        temporary.replace(target)
        (folder / LEGACY_FILE_NAME).unlink(missing_ok=True)
    except OSError:
        return False
    return True
