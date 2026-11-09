"""Geração de parcelas (D2, D8, D11, D17). Puro: o grupo vem de fora."""

from __future__ import annotations

import calendar
import datetime as dt

from money_cli.dominio.linha import LinhaInterpretada
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import NovoLancamento, Parcela


def data_da_parcela(primeira: dt.date, indice: int) -> dt.date:
    """Data da parcela `indice` (0 = primeira): mesmo dia, `indice` meses depois.

    Dia que o mês não tem vira o último dia do mês (31/01 -> 28/02).
    """
    mes = Mes.de(primeira).somar(indice)
    ultimo = calendar.monthrange(mes.ano, mes.mes)[1]
    return dt.date(mes.ano, mes.mes, min(primeira.day, ultimo))


def gerar(
    linha: LinhaInterpretada,
    conta_id: int,
    categoria_id: int | None,
    grupo: str | None,
) -> list[NovoLancamento]:
    """Transforma a linha em lançamentos: um, ou um por parcela em meses seguidos.

    O valor digitado é o de cada parcela (D11). `grupo` é obrigatório se há parcelas.
    """
    if linha.parcelas == 1:
        return [
            NovoLancamento(
                linha.data, linha.descricao, linha.valor, linha.tipo, conta_id, categoria_id
            )
        ]
    if not grupo:
        raise ValueError("parcelas precisam de um grupo")
    return [
        NovoLancamento(
            data_da_parcela(linha.data, i),
            linha.descricao,
            linha.valor,
            linha.tipo,
            conta_id,
            categoria_id,
            Parcela(grupo, i + 1, linha.parcelas),
        )
        for i in range(linha.parcelas)
    ]
