"""Tela principal do M2: contas, filtro, copiar, editar, paginação (critérios 1 a 11)."""

import datetime as dt

from textual.widgets import DataTable, Input, Static

from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import NovoLancamento, Parcela, Tipo
from money_cli.tela.app import POR_PAGINA, MoneyApp
from money_cli.tela.perguntas import EscolherCor, SoEstaOuTodas

HOJE = dt.date(2026, 11, 8)
NOV = Mes(2026, 11)


def _texto(app, seletor) -> str:
    return str(app.query_one(seletor, Static).render())


def _base(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    itau = banco.criar_conta("itaú", "#ff7a00")
    banco.criar_conta("parada", "#1f8fff")
    casa = banco.criar_categoria("casa")
    banco.criar_categoria("nubank")  # mesmo nome de conta: o filtro sem prefixo pede um
    banco.inserir_lancamentos(
        [
            NovoLancamento(dt.date(2026, 11, 5), "salário", 350000, Tipo.RECEITA, itau.id),
            NovoLancamento(dt.date(2026, 11, 6), "luz", 20000, Tipo.DESPESA, itau.id, casa.id),
            NovoLancamento(dt.date(2026, 11, 7), "mercado", 8990, Tipo.DESPESA, nubank.id),
            NovoLancamento(dt.date(2026, 10, 7), "sofá", 50000, Tipo.DESPESA, nubank.id, casa.id),
        ]
    )
    return nubank, itau, casa


async def test_topo_e_uma_linha_por_conta_com_movimento(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test():
        topo = _texto(app, "#topo")
        assert "3.500,00" in topo and "289,90" in topo and "3 lançamentos" in topo
        linhas = _texto(app, "#contas").splitlines()
        assert len(linhas) == 3  # todas as contas, em ordem de nome (D29)
        assert "itaú" in linhas[0] and "3.500,00" in linhas[0] and "200,00" in linhas[0]
        assert "nubank" in linhas[1] and "89,90" in linhas[1]
        assert "parada" in linhas[2] and "zerada" in linhas[2] and "receitas" not in linhas[2]


async def test_filtro_por_categoria_vale_para_tudo_e_segue_no_outro_mes(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("slash")
        campo = app.query_one("#linha", Input)
        assert campo.display and app.focused is campo
        campo.value = "#casa"
        await piloto.pause()
        assert "mostrar só #casa" in _texto(app, "#previa")
        await piloto.press("enter")
        await piloto.pause()
        assert not campo.display
        tabela = app.query_one("#lancamentos", DataTable)
        assert tabela.row_count == 1 and "luz" in str(tabela.get_row_at(0)[1])
        topo = _texto(app, "#topo")
        assert "filtro: #casa" in topo and "1 lançamento" in topo and "3.500" not in topo
        contas = _texto(app, "#contas").splitlines()  # nubank não tem #casa em novembro
        assert len(contas) == 3 and "zerada" in contas[1] and "200,00" in contas[0]

        await piloto.press("left")  # outubro: o filtro continua
        assert "sofá" in str(tabela.get_row_at(0)[1]) and "filtro: #casa" in _texto(app, "#topo")

        await piloto.press("escape")  # Esc na tela principal tira o filtro
        await piloto.pause()
        assert not app.filtro.ativo and "filtro" not in _texto(app, "#topo")


async def test_filtro_erros_e_enter_vazio(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("slash")
        campo = app.query_one("#linha", Input)
        campo.value = "nubank"
        await piloto.pause()
        assert "use @nubank ou #nubank" in _texto(app, "#previa")
        campo.value = "@nada"
        await piloto.press("enter")
        await piloto.pause()
        assert "não há a conta nada" in _texto(app, "#previa") and not app.filtro.ativo

        campo.value = "itaú"  # sem prefixo: só existe a conta
        await piloto.press("enter")
        await piloto.pause()
        assert app.filtro.conta_id == banco.conta_por_nome("itaú").id
        assert len(_texto(app, "#contas").splitlines()) == 1  # filtro por conta: só ela
        assert app.query_one("#lancamentos", DataTable).row_count == 2

        await piloto.press("slash")
        assert campo.value == "itaú"  # reabre com o filtro atual
        campo.value = ""
        await piloto.press("enter")
        await piloto.pause()
        assert not app.filtro.ativo
        assert app.query_one("#lancamentos", DataTable).row_count == 3


async def test_filtro_sem_resultado_avisa(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("slash")
        app.query_one("#linha", Input).value = "@parada"
        await piloto.press("enter")
        await piloto.pause()
        assert app.query_one("#vazio", Static).display
        assert "Esc tira o filtro" in _texto(app, "#vazio")


async def test_copiar_preenche_sem_data_e_cria_novo(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("left", "c")  # outubro: copia o sofá para hoje
        campo = app.query_one("#linha", Input)
        assert campo.value == "500,00 sofá #casa @nubank"
        assert "08/11/2026" in _texto(app, "#previa")
        await piloto.press("enter")
        await piloto.pause()
    assert [x.descricao for x in banco.lancamentos_do_mes(NOV)].count("sofá") == 1
    assert len(banco.lancamentos_do_mes(Mes(2026, 10))) == 1


async def test_editar_muda_o_mesmo_lancamento(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        tabela = app.query_one("#lancamentos", DataTable)
        await piloto.press("down")  # 2ª linha: luz (06/11)
        await piloto.press("e")
        await piloto.pause()
        campo = app.query_one("#linha", Input)
        assert campo.value == "200,00 luz #casa @itaú 06/11/2026"
        campo.value = "210,50 luz #casa @nova 04/11/2026"
        await piloto.pause()
        assert "editar:" in _texto(app, "#previa") and "@nova (nova)" in _texto(app, "#previa")
        await piloto.press("enter")
        await piloto.pause()
        assert isinstance(app.screen, EscolherCor)
        await piloto.press("enter")
        await piloto.pause()
        assert not campo.display and "editado" in _texto(app, "#previa")
        # O cursor segue o lançamento editado, que agora é o mais antigo do mês.
        assert "luz" in str(tabela.get_row_at(tabela.cursor_row)[1])
    itens = banco.lancamentos_do_mes(NOV)
    assert len(itens) == 3
    luz = next(x for x in itens if x.descricao == "luz")
    assert (luz.valor, luz.data) == (21050, dt.date(2026, 11, 4))
    assert luz.conta_id == banco.conta_por_nome("nova").id


async def test_editar_parcela_todas_e_erros(banco):
    nubank, itau, _ = _base(banco)
    grupo = banco.novo_grupo_parcela()
    banco.inserir_lancamentos(
        [
            NovoLancamento(
                dt.date(2026, 11 + i, 20),
                "tv",
                10000,
                Tipo.DESPESA,
                nubank.id,
                parcela=Parcela(grupo, i + 1, 2),
            )
            for i in range(2)
        ]
    )
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("e")  # 1ª linha: tv 1/2 (20/11)
        await piloto.pause()
        assert isinstance(app.screen, SoEstaOuTodas)
        await piloto.press("enter")  # todas
        await piloto.pause()
        campo = app.query_one("#linha", Input)
        assert campo.value == "100,00 tv @nubank"
        assert "todas as 2 parcelas" in _texto(app, "#previa")
        campo.value = "100,00 tv @nubank 3x"
        await piloto.pause()
        assert "parcelas não muda" in _texto(app, "#previa")
        campo.value = "100,00 tv @nubank 01/11"
        await piloto.press("enter")
        await piloto.pause()
        assert "a data muda só em um lançamento" in _texto(app, "#previa")
        campo.value = "150 televisão @itaú"
        await piloto.press("enter")
        await piloto.pause()
        assert "2 parcelas" in _texto(app, "#previa")
    for i, mes in enumerate([NOV, NOV.seguinte()]):
        tv = next(x for x in banco.lancamentos_do_mes(mes) if x.parcela)
        assert (tv.descricao, tv.valor, tv.conta_id) == ("televisão", 15000, itau.id)
        assert tv.data.day == 20 and tv.parcela.numero == i + 1


async def test_esc_na_edicao_nao_muda_nada(banco):
    _base(banco)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("e")
        app.query_one("#linha", Input).value = "1 x @itaú"
        await piloto.press("escape")
        await piloto.pause()
        await piloto.press("l")
        assert "editar" not in _texto(app, "#previa")
    assert banco.lancamentos_do_mes(NOV)[0].descricao == "mercado"


async def test_lista_longa_carrega_a_proxima_pagina(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    total = POR_PAGINA + 50
    banco.inserir_lancamentos(
        [
            NovoLancamento(dt.date(2026, 11, 1 + i % 28), f"item {i}", 100, Tipo.DESPESA, nubank.id)
            for i in range(total)
        ]
    )
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        tabela = app.query_one("#lancamentos", DataTable)
        assert tabela.row_count == POR_PAGINA and f"{total} lançamentos" in _texto(app, "#topo")
        await piloto.press("ctrl+end")
        await app.workers.wait_for_complete()
        await piloto.pause(0.1)
        assert tabela.row_count == total
        # Renomear lá embaixo mantém o cursor no mesmo item, mesmo após recarregar.
        alvo = tabela.cursor_row
        app.atualizar()
        assert tabela.cursor_row == alvo and tabela.row_count == total
