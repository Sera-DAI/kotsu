"""Parser da linha rápida (D10, D11). Puro: recebe texto e a data de hoje.

Sintaxe: o valor vem primeiro; o resto é livre.

    89,90 mercado #alimentação @nubank     despesa (sem sinal ou com -)
    +3500 salário @itaú                    receita
    120 geladeira #casa @nubank 10x        10 parcelas de 120,00, uma por mês
    ... ontem | 15/10 | 15/10/2025         data (padrão: hoje)
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from money_cli.dominio import dinheiro
from money_cli.dominio.tipos import Tipo

MAX_PARCELAS = 120

_PARCELAS = re.compile(r"(\d+)[xX]")
_DATA = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?")
_VALOR = re.compile(r"([+-]?)(.+)")
_DIGITOS = re.compile(r"\d+")
_MILHAR = re.compile(r"\d{1,3}(\.\d{3})+")


class ErroDeLinha(ValueError):
    """Linha que não dá para salvar. A mensagem é mostrada ao usuário como está."""


@dataclass(frozen=True, slots=True)
class LinhaInterpretada:
    """O que a linha diz, antes de resolver nomes de conta e categoria em ids."""

    valor: int  # centavos, positivo; de cada parcela quando há parcelas (D11)
    tipo: Tipo
    descricao: str
    data: dt.date
    categoria: str | None = None
    conta: str | None = None
    parcelas: int = 1
    com_data: bool = False  # a data foi escrita na linha (senão é hoje)

    @property
    def total(self) -> int:
        return self.valor * self.parcelas


def interpretar(linha: str, hoje: dt.date) -> LinhaInterpretada:
    """Lê uma linha rápida. Levanta `ErroDeLinha` com mensagem para o usuário."""
    partes = linha.split()
    if not partes:
        raise ErroDeLinha("digite o valor primeiro, ex.: 89,90 mercado @nubank")

    tipo, valor = _ler_valor(partes[0])
    descricao: list[str] = []
    categoria = conta = None
    data: dt.date | None = None
    parcelas: int | None = None

    for parte in partes[1:]:
        if parte.startswith("#"):
            if categoria is not None:
                raise ErroDeLinha("só uma #categoria por lançamento")
            categoria = _nome(parte, "categoria")
        elif parte.startswith("@"):
            if conta is not None:
                raise ErroDeLinha("só uma @conta por lançamento")
            conta = _nome(parte, "conta")
        elif m := _PARCELAS.fullmatch(parte):
            if parcelas is not None:
                raise ErroDeLinha("só um número de parcelas (ex.: 10x)")
            parcelas = int(m.group(1))
            if not 2 <= parcelas <= MAX_PARCELAS:
                raise ErroDeLinha(f"parcelas vão de 2x a {MAX_PARCELAS}x")
        elif (d := _ler_data(parte, hoje)) is not None:
            if data is not None:
                raise ErroDeLinha("só uma data por lançamento")
            data = d
        else:
            descricao.append(parte)

    return LinhaInterpretada(
        valor=valor,
        tipo=tipo,
        descricao=" ".join(descricao),
        data=data or hoje,
        categoria=categoria,
        conta=conta,
        parcelas=parcelas or 1,
        com_data=data is not None,
    )


def _nome(parte: str, oque: str) -> str:
    nome = parte[1:]
    if not nome:
        raise ErroDeLinha(f"falta o nome da {oque} depois de {parte[0]}")
    return nome


def _ler_valor(texto: str) -> tuple[Tipo, int]:
    m = _VALOR.fullmatch(texto)
    if not m:
        raise ErroDeLinha(f"valor ilegível: {texto} (use 89,90 ou 1.234,56)")
    sinal, numero = m.groups()
    tipo = Tipo.RECEITA if sinal == "+" else Tipo.DESPESA
    centavos = _centavos(numero)
    if centavos is None:
        raise ErroDeLinha(f"valor ilegível: {texto} (use 89,90 ou 1.234,56)")
    if centavos == 0:
        raise ErroDeLinha("o valor precisa ser maior que zero")
    return tipo, centavos


def _centavos(numero: str) -> int | None:
    """'89,90' '89.90' '89' '1.234,56' '1234,5' -> centavos. Ilegível -> None.

    Vírgula é sempre decimal e ponto, milhar. Sem vírgula, um ponto seguido de 1 ou 2
    dígitos no fim é decimal (89.90); em grupos de 3 é milhar (1.234).
    """
    if "," in numero:
        inteiro, _, fracao = numero.partition(",")
    elif re.fullmatch(r"\d+\.\d{1,2}", numero):
        inteiro, _, fracao = numero.partition(".")
    else:
        inteiro, fracao = numero, ""
    if "." in inteiro:
        if not _MILHAR.fullmatch(inteiro):
            return None
        inteiro = inteiro.replace(".", "")
    if not _DIGITOS.fullmatch(inteiro) or (fracao and not _DIGITOS.fullmatch(fracao)):
        return None
    if len(fracao) > 2:
        return None
    return int(inteiro) * 100 + int(fracao.ljust(2, "0") or 0)


def _ler_data(texto: str, hoje: dt.date) -> dt.date | None:
    """'hoje', 'ontem', 'dd/mm', 'dd/mm/aa', 'dd/mm/aaaa'. Não é data -> None."""
    minusculo = texto.casefold()
    if minusculo == "hoje":
        return hoje
    if minusculo == "ontem":
        return hoje - dt.timedelta(days=1)
    m = _DATA.fullmatch(texto)
    if not m:
        return None
    dia, mes, ano = m.groups()
    ano_num = hoje.year if ano is None else int(ano) + (2000 if len(ano) == 2 else 0)
    try:
        return dt.date(ano_num, int(mes), int(dia))
    except ValueError:
        raise ErroDeLinha(f"data impossível: {texto}") from None


def montar(
    valor: int,
    tipo: Tipo,
    descricao: str,
    conta: str,
    categoria: str | None = None,
    data: dt.date | None = None,
) -> str:
    """O caminho inverso de `interpretar`: a linha que copiar e editar mostram (D27, D28).

    Sem `data`, a linha não traz data (fica hoje ao salvar). Nunca traz parcelas.
    """
    partes = [("+" if tipo is Tipo.RECEITA else "") + dinheiro.formatar(valor)]
    if descricao:
        partes.append(descricao)
    if categoria:
        partes.append(f"#{categoria}")
    partes.append(f"@{conta}")
    if data is not None:
        partes.append(data.strftime("%d/%m/%Y"))
    return " ".join(partes)
