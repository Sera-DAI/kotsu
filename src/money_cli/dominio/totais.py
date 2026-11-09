"""Totais do mês. Nunca gravados: o armazenamento calcula e entrega aqui."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TotaisMes:
    receitas: int = 0
    despesas: int = 0
    quantidade: int = 0  # lançamentos do mês (ou do filtro)

    @property
    def saldo(self) -> int:
        """Receitas menos despesas do mês (D8)."""
        return self.receitas - self.despesas
