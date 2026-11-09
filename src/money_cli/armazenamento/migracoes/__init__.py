"""Migrações numeradas: arquivos NNNN_nome.sql nesta pasta, aplicados em ordem."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

_PADRAO = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True, slots=True)
class Migracao:
    versao: int
    nome: str
    sql: str


def carregar() -> list[Migracao]:
    """Lê as migrações do pacote e confere que a numeração é 1, 2, 3... sem buracos."""
    encontradas = []
    for item in resources.files(__package__).iterdir():
        casamento = _PADRAO.match(item.name)
        if casamento:
            encontradas.append(
                Migracao(int(casamento.group(1)), item.name, item.read_text(encoding="utf-8"))
            )
    encontradas.sort(key=lambda m: m.versao)
    for esperado, migracao in enumerate(encontradas, start=1):
        if migracao.versao != esperado:
            raise RuntimeError(f"migração {esperado:04d} faltando antes de {migracao.nome}")
    return encontradas
