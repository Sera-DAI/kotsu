"""Where the user's data lives."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

FILE_NAME = "kotsu.sqlite"
CONFIG_NAME = "local.toml"
ENV_VAR = "KOTSU_DATA"
# Names used before the product was called Kotsu. Only read to upgrade old installs.
_OLD_FOLDER = "money-cli"
_OLD_PREFIX = "money"


def _base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))


def local_folder() -> Path:
    """This computer's own folder: %APPDATA%\\kotsu or ~/.local/share/kotsu.

    Never synced: holds `local.toml` (where the data is) and, when the data is in a synced
    folder, the backups (D38). A folder left by an old version is renamed to `kotsu` the
    first time it is needed.
    """
    folder = _base() / "kotsu"
    legacy = _base() / _OLD_FOLDER
    if not folder.exists() and legacy.is_dir():
        try:
            legacy.rename(folder)
        except OSError:
            return legacy
    return folder


def _env_folder() -> str | None:
    return os.environ.get(ENV_VAR) or None


def configured_folder() -> Path | None:
    """`data_folder` from `local.toml`, or None (missing, unreadable or invalid)."""
    try:
        with (local_folder() / CONFIG_NAME).open("rb") as file:
            config = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = config.get("data_folder", config.get("pasta_dados"))
    return Path(value) if isinstance(value, str) and value.strip() else None


def save_configured_folder(folder: Path | None) -> None:
    """Saves (or, with None, deletes) this computer's data folder. Raises OSError."""
    target = local_folder() / CONFIG_NAME
    if folder is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".toml.tmp")
    # json.dumps produces a valid TOML string (backslashes and accents escaped).
    temporary.write_text(f"data_folder = {json.dumps(str(folder))}\n", encoding="utf-8")
    temporary.replace(target)


def data_folder() -> Path:
    """Data folder: KOTSU_DATA, or `local.toml`, or this computer's local folder."""
    explicit = _env_folder()
    if explicit:
        return Path(explicit)
    return configured_folder() or local_folder()


def backups_folder(data: Path) -> Path | None:
    """Backups outside the synced folder when the folder comes from `local.toml` (D38).

    None = default (`backups/` next to the database).
    """
    if _env_folder():
        return None
    if data == configured_folder():
        return local_folder() / "backups"
    return None


def database_file(folder: Path | None = None) -> Path:
    folder = folder or data_folder()
    upgrade_old_names(folder)
    upgrade_old_names(local_folder() / "backups")
    return folder / FILE_NAME


def upgrade_old_names(folder: Path) -> list[Path]:
    """Renames files left by old versions (`money.sqlite`, its copies and backups) to `kotsu.*`.

    Runs on every open and does nothing once done. A file is never overwritten: when the new
    name already exists, the old file stays where it is. Returns the renamed files.
    """
    renamed: list[Path] = []
    for folder_ in (folder, folder / "backups"):
        try:
            items = sorted(folder_.iterdir())
        except OSError:
            continue
        for old in items:
            name = old.name
            if not (old.is_file() and name.startswith(_OLD_PREFIX) and ".sqlite" in name):
                continue
            rest = name[len(_OLD_PREFIX) :]
            if not rest.startswith((".", " ", "-")):
                continue
            new = old.with_name("kotsu" + rest)
            if new.exists():
                continue
            try:
                old.rename(new)
            except OSError:
                continue
            renamed.append(new)
    return renamed
