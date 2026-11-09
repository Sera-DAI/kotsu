"""Tipos do domínio. Dinheiro é sempre em centavos inteiros (BRL)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class Tipo(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"


class Alcance(StrEnum):
    """Resposta a "só esta ou todas?" ao mexer numa parcela (D12). Padrão: todas."""

    SO_ESTA = "so_esta"
    TODAS = "todas"
    PROXIMAS = "proximas"  # recorrente: este mês e os seguintes (D36)


@dataclass(frozen=True, slots=True)
class Conta:
    """Etiqueta colorida (D9): não acumula saldo entre meses."""

    id: int
    nome: str
    cor: str


@dataclass(frozen=True, slots=True)
class Categoria:
    id: int
    nome: str
    recorrente: bool = False  # lançamentos nela se repetem todo mês (D36)


@dataclass(frozen=True, slots=True)
class Parcela:
    """Posição de um lançamento dentro de uma compra parcelada (D2, D8)."""

    grupo: str
    numero: int
    total: int

    def __post_init__(self) -> None:
        if not 1 <= self.numero <= self.total:
            raise ValueError(f"parcela {self.numero}/{self.total} inválida")

    @property
    def rotulo(self) -> str:
        return f"{self.numero}/{self.total}"


@dataclass(frozen=True, slots=True)
class NovoLancamento:
    """Lançamento ainda não salvo. `valor` é positivo; o sinal vem de `tipo`.

    Todo lançamento tem conta (D21); categoria é opcional.
    """

    data: dt.date
    descricao: str
    valor: int
    tipo: Tipo
    conta_id: int
    categoria_id: int | None = None
    parcela: Parcela | None = None
    grupo_recorrencia: str | None = None  # série mensal sem fim (D36)

    def __post_init__(self) -> None:
        if not isinstance(self.valor, int) or isinstance(self.valor, bool):
            raise TypeError("valor deve ser int em centavos")
        if self.valor <= 0:
            raise ValueError("valor deve ser positivo; o tipo diz se é receita ou despesa")
        if not isinstance(self.conta_id, int) or isinstance(self.conta_id, bool):
            raise ValueError("todo lançamento precisa de uma conta")


@dataclass(frozen=True, slots=True)
class Lancamento:
    id: int
    data: dt.date
    descricao: str
    valor: int
    tipo: Tipo
    conta_id: int
    categoria_id: int | None
    parcela: Parcela | None
    grupo_recorrencia: str | None = None

    @property
    def valor_com_sinal(self) -> int:
        return self.valor if self.tipo is Tipo.RECEITA else -self.valor
