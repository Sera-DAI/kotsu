"""Preferências do usuário em `tema.toml`, na pasta de dados. Erro nunca impede o app."""

from __future__ import annotations

import tomllib
from pathlib import Path

NOME_ARQUIVO = "tema.toml"


def ler_tema(pasta: Path) -> str | None:
    """Nome do tema salvo, ou None se o arquivo não existe, está ilegível ou sem `tema`."""
    try:
        with (pasta / NOME_ARQUIVO).open("rb") as arquivo:
            nome = tomllib.load(arquivo).get("tema")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return nome if isinstance(nome, str) else None


def gravar_tema(pasta: Path, nome: str) -> bool:
    """Grava o tema por arquivo temporário e troca atômica. False se não foi possível."""
    destino = pasta / NOME_ARQUIVO
    temporario = destino.with_suffix(".toml.tmp")
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        temporario.write_text(f'tema = "{nome}"\n', encoding="utf-8")
        temporario.replace(destino)
    except OSError:
        return False
    return True
