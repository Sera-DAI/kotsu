"""Datas de lançamentos recorrentes (D36). Puro: sem banco."""

from __future__ import annotations

import calendar
import datetime as dt

from money_cli.dominio.mes import Mes


def data_no_mes(dia: int, mes: Mes) -> dt.date:
    """O `dia` no mês; dia que o mês não tem vira o último (31 -> 28/02)."""
    ultimo = calendar.monthrange(mes.ano, mes.mes)[1]
    return dt.date(mes.ano, mes.mes, min(dia, ultimo))


def meses_a_gerar(gerada_ate: Mes, ate: Mes) -> list[Mes]:
    """Meses depois de `gerada_ate` até `ate`, inclusive. Vazio se já está gerado."""
    quantos = (ate.ano * 12 + ate.mes) - (gerada_ate.ano * 12 + gerada_ate.mes)
    return [gerada_ate.somar(i) for i in range(1, quantos + 1)]
