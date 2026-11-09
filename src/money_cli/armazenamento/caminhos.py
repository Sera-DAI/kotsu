"""Onde ficam os dados do usuário."""

from __future__ import annotations

import os
import sys
from pathlib import Path

NOME_ARQUIVO = "money.sqlite"


def pasta_de_dados() -> Path:
    """Pasta de dados: MONEY_CLI_DADOS, ou %APPDATA%\\money-cli, ou ~/.local/share/money-cli."""
    explicita = os.environ.get("MONEY_CLI_DADOS")
    if explicita:
        return Path(explicita)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "money-cli"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "money-cli"


def arquivo_do_banco(pasta: Path | None = None) -> Path:
    return (pasta or pasta_de_dados()) / NOME_ARQUIVO
