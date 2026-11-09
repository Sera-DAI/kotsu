"""Filtro da tela principal (D12, D26). Puro: lê o texto; a tela resolve os nomes."""

from __future__ import annotations

from dataclasses import dataclass

from money_cli.dominio.linha import ErroDeLinha


@dataclass(frozen=True, slots=True)
class FiltroDigitado:
    """O que foi digitado depois de `/`, antes de virar ids."""

    conta: str | None = None  # @nome
    categoria: str | None = None  # #nome
    qualquer: str | None = None  # nome sem prefixo: conta ou categoria

    @property
    def vazio(self) -> bool:
        return self.conta is None and self.categoria is None and self.qualquer is None


@dataclass(frozen=True, slots=True)
class Filtro:
    """Filtro já resolvido em ids. Vale o "e" entre conta e categoria."""

    conta_id: int | None = None
    categoria_id: int | None = None

    @property
    def ativo(self) -> bool:
        return self.conta_id is not None or self.categoria_id is not None


SEM_FILTRO = Filtro()


def interpretar_filtro(texto: str) -> FiltroDigitado:
    """`@nubank`, `#casa`, `@nubank #casa` ou `nubank`. Levanta `ErroDeLinha`."""
    conta = categoria = qualquer = None
    soltas: list[str] = []
    for parte in texto.split():
        if parte.startswith("@"):
            if conta is not None:
                raise ErroDeLinha("só uma @conta no filtro")
            conta = _nome(parte, "conta")
        elif parte.startswith("#"):
            if categoria is not None:
                raise ErroDeLinha("só uma #categoria no filtro")
            categoria = _nome(parte, "categoria")
        else:
            soltas.append(parte)
    if soltas:
        if conta is not None or categoria is not None:
            raise ErroDeLinha("use @conta e #categoria juntos, ou só um nome")
        qualquer = " ".join(soltas)
    return FiltroDigitado(conta, categoria, qualquer)


def _nome(parte: str, oque: str) -> str:
    if len(parte) == 1:
        raise ErroDeLinha(f"falta o nome da {oque} depois de {parte}")
    return parte[1:]
