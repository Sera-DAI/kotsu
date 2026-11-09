"""M2 sem tela: filtro, montar a linha e consultas do banco (critério 13)."""

import datetime as dt

import pytest

from money_cli.dominio.filtro import Filtro, FiltroDigitado, interpretar_filtro
from money_cli.dominio.linha import ErroDeLinha, interpretar, montar
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import Alcance, NovoLancamento, Parcela, Tipo
from money_cli.dominio.totais import TotaisMes

HOJE = dt.date(2026, 11, 8)
NOV = Mes(2026, 11)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("@nubank", FiltroDigitado(conta="nubank")),
        ("#casa", FiltroDigitado(categoria="casa")),
        ("@nubank #casa", FiltroDigitado(conta="nubank", categoria="casa")),
        ("  nubank ", FiltroDigitado(qualquer="nubank")),
        ("", FiltroDigitado()),
    ],
)
def test_interpretar_filtro(texto, esperado):
    assert interpretar_filtro(texto) == esperado


@pytest.mark.parametrize("texto", ["@a @b", "#a #b", "@", "#", "@nubank casa"])
def test_filtro_invalido(texto):
    with pytest.raises(ErroDeLinha):
        interpretar_filtro(texto)


def test_filtro_vazio_nao_esta_ativo():
    assert interpretar_filtro("").vazio
    assert not Filtro().ativo and Filtro(conta_id=1).ativo


@pytest.mark.parametrize(
    ("args", "texto"),
    [
        (
            (8990, Tipo.DESPESA, "mercado", "nubank", "alimentação", None),
            "89,90 mercado #alimentação @nubank",
        ),
        (
            (350000, Tipo.RECEITA, "salário", "itaú", None, dt.date(2025, 10, 3)),
            "+3.500,00 salário @itaú 03/10/2025",
        ),
        ((123456, Tipo.DESPESA, "", "nubank", None, None), "1.234,56 @nubank"),
    ],
)
def test_montar_e_interpretar_de_volta(args, texto):
    valor, tipo, descricao, conta, categoria, data = args
    linha = montar(valor, tipo, descricao, conta, categoria, data)
    assert linha == texto
    volta = interpretar(linha, HOJE)
    assert (volta.valor, volta.tipo, volta.descricao) == (valor, tipo, descricao)
    assert (volta.conta, volta.categoria, volta.parcelas) == (conta, categoria, 1)
    assert volta.data == (data or HOJE) and volta.com_data == (data is not None)


def _base(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    itau = banco.criar_conta("itaú", "#ff7a00")
    banco.criar_conta("parada", "#1f8fff")
    casa = banco.criar_categoria("casa")
    banco.inserir_lancamentos(
        [
            NovoLancamento(dt.date(2026, 11, 5), "salário", 350000, Tipo.RECEITA, itau.id),
            NovoLancamento(dt.date(2026, 11, 6), "luz", 20000, Tipo.DESPESA, itau.id, casa.id),
            NovoLancamento(dt.date(2026, 11, 7), "mercado", 8990, Tipo.DESPESA, nubank.id),
            NovoLancamento(dt.date(2026, 11, 8), "sofá", 50000, Tipo.DESPESA, nubank.id, casa.id),
            NovoLancamento(dt.date(2026, 10, 8), "outubro", 100, Tipo.DESPESA, nubank.id),
        ]
    )
    return nubank, itau, casa


def test_totais_por_conta_somam_o_topo(banco):
    nubank, itau, _ = _base(banco)
    por_conta = banco.totais_por_conta(NOV)
    assert por_conta == {
        nubank.id: TotaisMes(0, 58990, 2),
        itau.id: TotaisMes(350000, 20000, 2),
    }  # "parada" não teve lançamento: não aparece (D29)
    topo = banco.totais_do_mes(NOV)
    assert sum(t.receitas for t in por_conta.values()) == topo.receitas
    assert sum(t.despesas for t in por_conta.values()) == topo.despesas


def test_filtro_vale_para_totais_e_lista(banco):
    nubank, itau, casa = _base(banco)
    so_casa = Filtro(categoria_id=casa.id)
    assert banco.totais_do_mes(NOV, so_casa) == TotaisMes(0, 70000, 2)
    assert [x.descricao for x in banco.lancamentos_do_mes(NOV, filtro=so_casa)] == ["sofá", "luz"]
    assert banco.totais_por_conta(NOV, so_casa).keys() == {nubank.id, itau.id}
    ambos = Filtro(conta_id=nubank.id, categoria_id=casa.id)
    assert [x.descricao for x in banco.lancamentos_do_mes(NOV, filtro=ambos)] == ["sofá"]


def test_editar_lancamento_simples_muda_tudo_inclusive_data(banco):
    nubank, itau, casa = _base(banco)
    mercado = next(x for x in banco.lancamentos_do_mes(NOV) if x.descricao == "mercado")
    novo = NovoLancamento(dt.date(2026, 12, 1), "feira", 4500, Tipo.RECEITA, itau.id, casa.id)
    assert banco.editar(mercado.id, novo) == 1
    editado = banco.lancamento(mercado.id)
    assert (editado.data, editado.descricao, editado.valor) == (dt.date(2026, 12, 1), "feira", 4500)
    assert (editado.tipo, editado.conta_id, editado.categoria_id) == (
        Tipo.RECEITA,
        itau.id,
        casa.id,
    )


def test_editar_parcelas_todas_mantem_datas_e_so_esta_muda_uma(banco):
    nubank, itau, casa = _base(banco)
    grupo = banco.novo_grupo_parcela()
    ids = banco.inserir_lancamentos(
        [
            NovoLancamento(
                dt.date(2026, 11 + i, 2),
                "tv",
                10000,
                Tipo.DESPESA,
                nubank.id,
                parcela=Parcela(grupo, i + 1, 2),
            )
            for i in range(2)
        ]
    )
    novo = NovoLancamento(HOJE, "televisão", 12000, Tipo.DESPESA, itau.id, casa.id)
    assert banco.editar(ids[0], novo, Alcance.TODAS) == 2
    todas = [banco.lancamento(i) for i in ids]
    assert [x.data for x in todas] == [dt.date(2026, 11, 2), dt.date(2026, 12, 2)]
    assert {(x.descricao, x.valor, x.conta_id, x.parcela.total) for x in todas} == {
        ("televisão", 12000, itau.id, 2)
    }
    so = NovoLancamento(dt.date(2026, 12, 20), "tv", 9000, Tipo.DESPESA, itau.id)
    assert banco.editar(ids[1], so, Alcance.SO_ESTA) == 1
    assert banco.lancamento(ids[1]).data == dt.date(2026, 12, 20)
    assert banco.lancamento(ids[0]).valor == 12000
