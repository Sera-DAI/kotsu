"""Parser da linha rápida e geração de parcelas (critérios 1 a 7 do M1)."""

import datetime as dt

import pytest

from money_cli.dominio import parcelas
from money_cli.dominio.linha import ErroDeLinha, LinhaInterpretada, interpretar
from money_cli.dominio.tipos import Tipo

HOJE = dt.date(2026, 11, 8)


def test_exemplo_despesa_com_categoria_e_conta():
    linha = interpretar("89,90 mercado #alimentação @nubank", HOJE)
    assert linha == LinhaInterpretada(
        valor=8990,
        tipo=Tipo.DESPESA,
        descricao="mercado",
        data=HOJE,
        categoria="alimentação",
        conta="nubank",
    )


def test_exemplo_receita():
    linha = interpretar("+3500 salário @itaú", HOJE)
    assert (linha.tipo, linha.valor, linha.descricao, linha.conta) == (
        Tipo.RECEITA,
        350000,
        "salário",
        "itaú",
    )
    assert linha.categoria is None


def test_exemplo_parcelado_valor_e_de_cada_parcela():
    linha = interpretar("120 geladeira #casa @nubank 10x", HOJE)
    assert (linha.valor, linha.parcelas, linha.total) == (12000, 10, 120000)


def test_ordem_livre_depois_do_valor():
    a = interpretar("120 @nubank 3x geladeira #casa nova", HOJE)
    assert (a.descricao, a.conta, a.categoria, a.parcelas) == (
        "geladeira nova",
        "nubank",
        "casa",
        3,
    )


@pytest.mark.parametrize(
    ("texto", "centavos"),
    [
        ("89,90", 8990),
        ("89.90", 8990),
        ("89,9", 8990),
        ("89", 8900),
        ("0,05", 5),
        ("1.234,56", 123456),
        ("1.234", 123400),
        ("1234,56", 123456),
        ("-89,90", 8990),
        ("+1.000.000", 100000000),
    ],
)
def test_formatos_de_valor(texto, centavos):
    assert interpretar(f"{texto} x", HOJE).valor == centavos


def test_menos_explicito_e_despesa():
    assert interpretar("-89,90 x", HOJE).tipo is Tipo.DESPESA


@pytest.mark.parametrize(
    "texto",
    ["", "   ", "mercado 89,90", "0", "0,00", "89,901", "1.23.4", "12a", "+", "-", "1,2,3"],
)
def test_valor_invalido_vira_erro(texto):
    with pytest.raises(ErroDeLinha):
        interpretar(texto, HOJE)


@pytest.mark.parametrize(
    ("texto", "data"),
    [
        ("10 x", HOJE),
        ("10 x hoje", HOJE),
        ("10 x ontem", dt.date(2026, 11, 7)),
        ("10 x Ontem", dt.date(2026, 11, 7)),
        ("10 x 15/10", dt.date(2026, 10, 15)),
        ("10 x 5/1", dt.date(2026, 1, 5)),
        ("10 x 15/10/2025", dt.date(2025, 10, 15)),
        ("10 x 15/10/25", dt.date(2025, 10, 15)),
    ],
)
def test_datas(texto, data):
    assert interpretar(texto, HOJE).data == data


def test_ontem_no_dia_primeiro_volta_o_mes():
    assert interpretar("10 ontem", dt.date(2026, 3, 1)).data == dt.date(2026, 2, 28)


@pytest.mark.parametrize(
    ("texto", "trecho"),
    [
        ("10 x 31/02", "data impossível"),
        ("10 x 15/13", "data impossível"),
        ("10 #a #b", "só uma #categoria"),
        ("10 @a @b", "só uma @conta"),
        ("10 x 2x 3x", "só um número de parcelas"),
        ("10 x ontem 15/10", "só uma data"),
        ("10 x 1x", "2x a 120x"),
        ("10 x 121x", "2x a 120x"),
        ("10 x #", "falta o nome da categoria"),
        ("10 x @", "falta o nome da conta"),
    ],
)
def test_erros_tem_mensagem(texto, trecho):
    with pytest.raises(ErroDeLinha, match=trecho):
        interpretar(texto, HOJE)


def test_descricao_pode_ficar_vazia():
    assert interpretar("+3500 @itaú", HOJE).descricao == ""


def test_parcelas_em_meses_seguidos_mesmo_grupo():
    linha = interpretar("120 geladeira #casa @nubank 10x", HOJE)
    novos = parcelas.gerar(linha, conta_id=1, categoria_id=2, grupo="g")
    assert len(novos) == 10
    assert [n.data for n in novos][:3] == [
        dt.date(2026, 11, 8),
        dt.date(2026, 12, 8),
        dt.date(2027, 1, 8),
    ]
    assert novos[-1].data == dt.date(2027, 8, 8)
    assert {n.valor for n in novos} == {12000}
    assert {n.parcela.grupo for n in novos} == {"g"}
    assert [n.parcela.rotulo for n in novos] == [f"{i}/10" for i in range(1, 11)]
    assert all(n.conta_id == 1 and n.categoria_id == 2 for n in novos)


def test_dia_que_o_mes_nao_tem_vira_ultimo_dia():
    assert parcelas.data_da_parcela(dt.date(2027, 1, 31), 1) == dt.date(2027, 2, 28)
    assert parcelas.data_da_parcela(dt.date(2028, 1, 31), 1) == dt.date(2028, 2, 29)
    assert parcelas.data_da_parcela(dt.date(2027, 1, 31), 2) == dt.date(2027, 3, 31)


def test_lancamento_simples_nao_tem_parcela():
    (novo,) = parcelas.gerar(interpretar("10 x", HOJE), 1, None, None)
    assert novo.parcela is None


def test_parcelas_sem_grupo_e_erro_de_programa():
    with pytest.raises(ValueError):
        parcelas.gerar(interpretar("10 x 3x", HOJE), 1, None, None)
