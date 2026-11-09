"""Temas da tela (D37): Algodão-Doce claro e noite. Só cores e enfeites, sem regra de negócio."""

from __future__ import annotations

from dataclasses import dataclass

from textual.theme import Theme


@dataclass(frozen=True)
class Tema:
    nome: str  # identificador gravado em tema.toml
    rotulo: str
    escuro: bool
    fundo: str
    superficie: str
    painel: str
    texto: str
    destaque: str  # rosa: título, cabeçalho, cursor
    secundaria: str  # azul: rótulos do topo
    aviso: str  # dourado: rostinho
    receita: str
    despesa: str
    neutro: str
    # Enfeites.
    marcador: str = "♡"
    zerada: str = "zzz… zerada"
    barra_cheia: str = "♥"
    barra_vazia: str = "·"
    feliz: str = "(◕‿◕)♡"
    triste: str = "(；ω；)"

    def para_textual(self) -> Theme:
        return Theme(
            name=self.nome,
            primary=self.destaque,
            secondary=self.secundaria,
            accent=self.aviso,
            background=self.fundo,
            surface=self.superficie,
            panel=self.painel,
            foreground=self.texto,
            success=self.receita,
            error=self.despesa,
            warning=self.aviso,
            dark=self.escuro,
        )


ALGODAO_NOITE = Tema(
    nome="algodao-noite", rotulo="Algodão-Doce noite", escuro=True,
    fundo="#1d1424", superficie="#291b33", painel="#41274f", texto="#ffe9f4",
    destaque="#ff7fb8", secundaria="#8fb3ff", aviso="#ffd27a",
    receita="#86efc0", despesa="#ff7a9e", neutro="#9a7fa8",
)  # fmt: skip

ALGODAO_CLARO = Tema(
    nome="algodao-claro", rotulo="Algodão-Doce claro", escuro=False,
    fundo="#fff5fa", superficie="#ffeaf4", painel="#ffd6e8", texto="#5a3a5e",
    destaque="#e0509a", secundaria="#4f74c7", aviso="#b87400",
    receita="#1f9d6b", despesa="#d6336c", neutro="#8f6f8c",
)  # fmt: skip

TEMAS = (ALGODAO_NOITE, ALGODAO_CLARO)
PADRAO = ALGODAO_NOITE


def tema_por_nome(nome: str | None) -> Tema:
    """Tema de nome conhecido; qualquer outra coisa volta ao padrão."""
    return next((t for t in TEMAS if t.nome == nome), PADRAO)


def proximo(atual: Tema) -> Tema:
    return TEMAS[(TEMAS.index(atual) + 1) % len(TEMAS)]
