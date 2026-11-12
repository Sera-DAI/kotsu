"""Onde ficam os dados do usuário."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

NOME_ARQUIVO = "money.sqlite"
NOME_CONFIG = "local.toml"


def pasta_local() -> Path:
    """Pasta própria deste computador: %APPDATA%\\money-cli ou ~/.local/share/money-cli.

    Nunca é sincronizada: guarda `local.toml` (onde estão os dados) e, quando os dados estão
    numa pasta sincronizada, os backups (D38).
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "money-cli"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "money-cli"


def pasta_configurada() -> Path | None:
    """`pasta_dados` do `local.toml`, ou None (ausente, ilegível ou inválido)."""
    try:
        with (pasta_local() / NOME_CONFIG).open("rb") as arquivo:
            valor = tomllib.load(arquivo).get("pasta_dados")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return Path(valor) if isinstance(valor, str) and valor.strip() else None


def gravar_pasta_configurada(pasta: Path | None) -> None:
    """Grava (ou, com None, apaga) a pasta de dados deste computador. Levanta OSError."""
    destino = pasta_local() / NOME_CONFIG
    if pasta is None:
        destino.unlink(missing_ok=True)
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".toml.tmp")
    # json.dumps gera uma string TOML válida (barras e acentos escapados).
    temporario.write_text(f"pasta_dados = {json.dumps(str(pasta))}\n", encoding="utf-8")
    temporario.replace(destino)


def pasta_de_dados() -> Path:
    """Pasta de dados: MONEY_CLI_DADOS, ou `local.toml`, ou a pasta local do computador."""
    explicita = os.environ.get("MONEY_CLI_DADOS")
    if explicita:
        return Path(explicita)
    return pasta_configurada() or pasta_local()


def pasta_de_backups(pasta_dados: Path) -> Path | None:
    """Backups fora da pasta sincronizada quando a pasta vem do `local.toml` (D38).

    None = padrão (`backups/` ao lado do banco).
    """
    if os.environ.get("MONEY_CLI_DADOS"):
        return None
    if pasta_dados == pasta_configurada():
        return pasta_local() / "backups"
    return None


def arquivo_do_banco(pasta: Path | None = None) -> Path:
    return (pasta or pasta_de_dados()) / NOME_ARQUIVO
