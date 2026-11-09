"""Mês civil, sem fuso. Cada mês é fechado em si (D9)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

NOMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


@dataclass(frozen=True, slots=True, order=True)
class Mes:
    ano: int
    mes: int

    def __post_init__(self) -> None:
        if not 1 <= self.mes <= 12:
            raise ValueError(f"mês inválido: {self.mes}")

    @classmethod
    def de(cls, data: dt.date) -> Mes:
        return cls(data.year, data.month)

    def somar(self, meses: int) -> Mes:
        indice = self.ano * 12 + (self.mes - 1) + meses
        return Mes(indice // 12, indice % 12 + 1)

    def anterior(self) -> Mes:
        return self.somar(-1)

    def seguinte(self) -> Mes:
        return self.somar(1)

    @property
    def inicio(self) -> dt.date:
        return dt.date(self.ano, self.mes, 1)

    @property
    def fim_exclusivo(self) -> dt.date:
        return self.seguinte().inicio

    @property
    def nome(self) -> str:
        return f"{NOMES[self.mes - 1]} de {self.ano}"
