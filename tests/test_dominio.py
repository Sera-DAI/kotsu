import datetime as dt

import pytest

from money_cli.dominio import dinheiro
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import Lancamento, NovoLancamento, Parcela, Tipo
from money_cli.dominio.totais import TotaisMes


@pytest.mark.parametrize(
    ("centavos", "texto"),
    [
        (0, "0,00"),
        (5, "0,05"),
        (8990, "89,90"),
        (123456, "1.234,56"),
        (100000000, "1.000.000,00"),
        (-8990, "89,90"),
    ],
)
def test_formatar_sem_sinal(centavos, texto):
    assert dinheiro.formatar(centavos) == texto


def test_mes_vira_o_ano():
    assert Mes(2026, 12).seguinte() == Mes(2027, 1)
    assert Mes(2026, 1).anterior() == Mes(2025, 12)
    assert Mes(2026, 11).somar(10) == Mes(2027, 9)
    assert Mes(2026, 11).somar(-23) == Mes(2024, 12)


def test_mes_limites_e_nome():
    m = Mes.de(dt.date(2026, 2, 17))
    assert (m.inicio, m.fim_exclusivo) == (dt.date(2026, 2, 1), dt.date(2026, 3, 1))
    assert m.nome == "fevereiro de 2026"
    with pytest.raises(ValueError):
        Mes(2026, 13)


def test_saldo_e_receitas_menos_despesas():
    assert TotaisMes(350000, 412000).saldo == -62000


def test_valor_tem_que_ser_centavos_positivos():
    hoje = dt.date(2026, 11, 8)
    with pytest.raises(TypeError):
        NovoLancamento(hoje, "x", 89.9, Tipo.DESPESA, 1)
    with pytest.raises(ValueError):
        NovoLancamento(hoje, "x", -8990, Tipo.DESPESA, 1)
    with pytest.raises(ValueError):
        NovoLancamento(hoje, "x", 0, Tipo.DESPESA, 1)


def test_todo_lancamento_tem_conta():
    hoje = dt.date(2026, 11, 8)
    assert NovoLancamento(hoje, "x", 100, Tipo.DESPESA, 1).categoria_id is None
    with pytest.raises(TypeError):
        NovoLancamento(hoje, "x", 100, Tipo.DESPESA)  # conta é obrigatória
    with pytest.raises(ValueError, match="conta"):
        NovoLancamento(hoje, "x", 100, Tipo.DESPESA, None)


def test_parcela():
    assert Parcela("g", 3, 10).rotulo == "3/10"
    with pytest.raises(ValueError):
        Parcela("g", 11, 10)


def test_sinal_vem_do_tipo():
    base = dict(
        id=1,
        data=dt.date(2026, 11, 8),
        descricao="x",
        valor=100,
        conta_id=1,
        categoria_id=None,
        parcela=None,
    )
    assert Lancamento(tipo=Tipo.RECEITA, **base).valor_com_sinal == 100
    assert Lancamento(tipo=Tipo.DESPESA, **base).valor_com_sinal == -100
