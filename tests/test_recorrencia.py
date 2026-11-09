"""Categorias recorrentes (D36): repetem todo mês, sem fim, até a pessoa encerrar."""

import datetime as dt
import sqlite3

from textual.widgets import DataTable, Input, Static

from money_cli.armazenamento.banco import Banco
from money_cli.dominio.mes import Mes
from money_cli.dominio.recorrencia import data_no_mes, meses_a_gerar
from money_cli.dominio.tipos import Alcance, NovoLancamento, Tipo
from money_cli.tela.app import MESES_A_FRENTE, MoneyApp
from money_cli.tela.perguntas import SimOuNao, SoEsteOuProximos

HOJE = dt.date(2026, 11, 8)


def _serie(banco, dia=dt.date(2026, 11, 4)):
    conta = banco.criar_conta("itaú", "#ff7a00")
    cat = banco.criar_categoria("aluguel", recorrente=True)
    (id_,) = banco.inserir_lancamentos(
        [
            NovoLancamento(
                dia, "aluguel", 150000, Tipo.DESPESA, conta.id, cat.id, grupo_recorrencia="g1"
            )
        ]
    )
    return id_


def test_datas_do_dominio():
    assert data_no_mes(31, Mes(2027, 2)) == dt.date(2027, 2, 28)
    assert data_no_mes(5, Mes(2027, 2)) == dt.date(2027, 2, 5)
    assert meses_a_gerar(Mes(2026, 11), Mes(2027, 1)) == [Mes(2026, 12), Mes(2027, 1)]
    assert meses_a_gerar(Mes(2026, 11), Mes(2026, 11)) == []
    assert meses_a_gerar(Mes(2026, 11), Mes(2026, 8)) == []


def test_estender_gera_ate_o_mes_e_nao_duplica(banco):
    _serie(banco)
    assert banco.estender_recorrencias(Mes(2027, 2)) == 3
    assert banco.estender_recorrencias(Mes(2027, 2)) == 0
    assert banco.estender_recorrencias(Mes(2026, 12)) == 0  # só avança
    for mes in (Mes(2026, 11), Mes(2026, 12), Mes(2027, 1), Mes(2027, 2)):
        (item,) = banco.lancamentos_do_mes(mes)
        assert item.valor == 150000 and item.data.day == 4


def test_dia_31_vira_ultimo_dia(banco):
    _serie(banco, dt.date(2026, 10, 31))
    banco.estender_recorrencias(Mes(2026, 12))
    datas = {i.data for m in (Mes(2026, 11), Mes(2026, 12)) for i in banco.lancamentos_do_mes(m)}
    assert datas == {dt.date(2026, 11, 30), dt.date(2026, 12, 31)}


def test_so_este_mes_nao_volta(banco):
    id_ = _serie(banco)
    banco.estender_recorrencias(Mes(2027, 1))
    (dez,) = banco.lancamentos_do_mes(Mes(2026, 12))
    banco.excluir(dez.id, Alcance.SO_ESTA)
    banco.estender_recorrencias(Mes(2027, 3))
    assert banco.lancamentos_do_mes(Mes(2026, 12)) == []
    assert len(banco.lancamentos_do_mes(Mes(2027, 3))) == 1
    assert banco.lancamento(id_) is not None


def test_proximos_encerra_e_preserva_o_passado(banco):
    _serie(banco)
    banco.estender_recorrencias(Mes(2027, 2))
    (jan,) = banco.lancamentos_do_mes(Mes(2027, 1))
    assert banco.excluir(jan.id, Alcance.PROXIMAS) == 2  # jan e fev
    banco.estender_recorrencias(Mes(2027, 6))
    assert len(banco.lancamentos_do_mes(Mes(2026, 12))) == 1
    assert banco.lancamentos_do_mes(Mes(2027, 1)) == []
    assert banco.lancamentos_do_mes(Mes(2027, 6)) == []


def test_editar_proximos_muda_modelo_e_meses_futuros(banco):
    _serie(banco)
    banco.estender_recorrencias(Mes(2027, 1))
    (dez,) = banco.lancamentos_do_mes(Mes(2026, 12))
    conta = banco.listar_contas()[0]
    novo = NovoLancamento(
        dez.data, "aluguel novo", 160000, Tipo.DESPESA, conta.id, dez.categoria_id
    )
    assert banco.editar(dez.id, novo, Alcance.PROXIMAS) == 2  # dez e jan
    banco.estender_recorrencias(Mes(2027, 3))
    assert banco.lancamentos_do_mes(Mes(2026, 11))[0].valor == 150000
    for mes in (Mes(2026, 12), Mes(2027, 3)):
        (item,) = banco.lancamentos_do_mes(mes)
        assert (item.valor, item.descricao) == (160000, "aluguel novo")


def test_tornar_recorrente_e_recusas(banco):
    conta = banco.criar_conta("itaú", "#ff7a00")
    (id_,) = banco.inserir_lancamentos(
        [NovoLancamento(dt.date(2026, 11, 5), "net", 9990, Tipo.DESPESA, conta.id)]
    )
    assert banco.tornar_recorrente(id_) is True
    assert banco.tornar_recorrente(id_) is False
    banco.estender_recorrencias(Mes(2026, 12))
    assert len(banco.lancamentos_do_mes(Mes(2026, 12))) == 1


def test_migracao_0002_preserva_dados(tmp_path):
    from money_cli.armazenamento import migracoes
    from money_cli.armazenamento.banco import migrar

    caminho = tmp_path / "money.sqlite"
    conexao = sqlite3.connect(caminho, isolation_level=None)
    migrar(conexao, caminho, migracoes.carregar()[:1])
    conexao.execute("INSERT INTO conta (nome, cor) VALUES ('a', '#fff')")
    conexao.execute("INSERT INTO categoria (nome) VALUES ('casa')")
    conexao.execute(
        "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id)"
        " VALUES ('2026-11-01', 'x', 100, 'despesa', 1, 1)"
    )
    conexao.close()
    banco = Banco.abrir(caminho)
    assert banco.versao >= 2
    assert banco.listar_categorias()[0].recorrente is False
    assert banco.lancamentos_do_mes(Mes(2026, 11))[0].grupo_recorrencia is None
    assert (tmp_path / "money.antes-v2.sqlite").exists()
    banco.fechar()


async def test_tela_categoria_nova_recorrente_e_navegacao(banco):
    banco.criar_conta("itaú", "#ff7a00")
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "1500 aluguel #moradia @itaú"
        await piloto.press("enter")
        await piloto.pause()
        assert isinstance(app.screen, SimOuNao)
        await piloto.press("enter")  # criar categoria
        await piloto.pause()
        assert isinstance(app.screen, SimOuNao)
        await piloto.press("enter")  # repetir todo mês
        await piloto.pause()
        assert banco.categoria_por_nome("moradia").recorrente
        await piloto.press("escape")
        await piloto.press("right", "right")
        await piloto.pause()
        assert len(banco.lancamentos_do_mes(Mes(2027, 1))) == 1
        tabela = app.query_one("#lancamentos", DataTable)
        assert "↻" in str(tabela.get_row_at(0)[1])


async def test_tela_parcelas_em_categoria_recorrente_sao_recusadas(banco):
    banco.criar_conta("itaú", "#ff7a00")
    banco.criar_categoria("moradia", recorrente=True)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "100 sofá #moradia @itaú 3x"
        await piloto.press("enter")
        await piloto.pause()
        assert "já repete todo mês" in str(app.query_one("#previa", Static).render())
        assert banco.lancamentos_do_mes(Mes(2026, 11)) == []


async def test_tela_excluir_pergunta_e_encerra(banco):
    _serie(banco, dt.date(2026, 11, 4))
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("right")
        await piloto.pause()
        await piloto.press("d")
        await piloto.pause()
        assert isinstance(app.screen, SoEsteOuProximos)
        await piloto.press("p")
        await piloto.pause()
        assert banco.lancamentos_do_mes(Mes(2026, 12)) == []
        assert len(banco.lancamentos_do_mes(Mes(2026, 11))) == 1


async def test_tela_limite_de_meses_a_frente(banco):
    _serie(banco, dt.date(2026, 11, 4))
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test():
        app.mes = Mes(2026, 11).somar(MESES_A_FRENTE + 10)
        app.atualizar(topo=True)
        assert banco.lancamentos_do_mes(Mes(2026, 11).somar(MESES_A_FRENTE + 5)) == []
        assert len(banco.lancamentos_do_mes(Mes(2026, 11).somar(MESES_A_FRENTE))) == 1
