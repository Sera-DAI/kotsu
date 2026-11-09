"""Linha rápida na tela: prévia, perguntas e exclusão (critérios 8 a 10)."""

import datetime as dt

from textual.widgets import DataTable, Input, Static

from money_cli.dominio.mes import Mes
from money_cli.tela import cores
from money_cli.tela.app import MoneyApp
from money_cli.tela.perguntas import EscolherCor, SimOuNao, SoEstaOuTodas

HOJE = dt.date(2026, 11, 8)


def _previa(app) -> str:
    return str(app.query_one("#previa", Static).render())


async def _digitar(piloto, texto):
    await piloto.press(*["space" if c == " " else c for c in texto])


async def test_conta_e_categoria_novas_perguntam_e_salvam(banco):
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        campo = app.query_one("#linha", Input)
        assert campo.display and app.focused is campo
        campo.value = "89,90 mercado #alimentação @nubank"
        await piloto.pause()
        previa = _previa(app)
        assert "despesa 89,90" in previa and "@nubank (nova)" in previa
        assert "#alimentação (nova)" in previa and "08/11/2026" in previa

        await piloto.press("enter")
        await piloto.pause()
        assert isinstance(app.screen, EscolherCor)
        await piloto.press("3")  # azul
        await piloto.pause()
        assert isinstance(app.screen, SimOuNao)
        await piloto.press("enter")
        await piloto.pause()
        assert isinstance(app.screen, SimOuNao)  # repetir todo mês? (D36)
        await piloto.press("n")
        await piloto.pause()

        (item,) = banco.lancamentos_do_mes(Mes(2026, 11))
        assert (item.valor, item.descricao) == (8990, "mercado")
        assert banco.conta_por_nome("nubank").cor == cores.CONTAS[2]
        assert banco.categoria_por_nome("alimentação").id == item.categoria_id
        assert campo.value == "" and app.focused is campo
        assert "salvo" in _previa(app)
        assert app.query_one("#lancamentos", DataTable).row_count == 1


async def test_esc_na_pergunta_nao_salva_nada(banco):
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "10 café @nova"
        await piloto.press("enter")
        await piloto.pause()
        await piloto.press("escape")
        await piloto.pause()
        assert banco.listar_contas() == []
        assert banco.lancamentos_do_mes(Mes(2026, 11)) == []
        assert "nada foi salvo" in _previa(app)


async def test_sem_conta_sempre_bloqueia_mesmo_com_lancamento_anterior(banco):
    banco.criar_conta("nubank", "#8a2be2")
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        campo = app.query_one("#linha", Input)
        campo.value = "5 pão @nubank"
        await piloto.press("enter")
        await piloto.pause()
        campo.value = "120 10x"
        await piloto.pause()
        assert "falta @conta" in _previa(app) and "nubank" not in _previa(app)
        await piloto.press("enter")
        await piloto.pause()
        assert "informe a conta com @nome" in _previa(app)
        assert campo.value == "120 10x"
    assert len(banco.lancamentos_do_mes(Mes(2026, 11))) == 1
    assert banco.lancamentos_do_mes(Mes(2026, 12)) == []


async def test_parcelas_pela_tela(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "120 10x @nubank"
        await piloto.pause()
        assert "10x de 120,00 = 1.200,00" in _previa(app)
        assert "nov/2026 a ago/2027" in _previa(app)
        await piloto.press("enter")
        await piloto.pause()
    for i in range(10):
        (item,) = banco.lancamentos_do_mes(Mes(2026, 11).somar(i))
        assert (item.valor, item.conta_id, item.parcela.rotulo) == (12000, nubank.id, f"{i + 1}/10")


async def test_digitar_letras_de_atalho_vai_para_a_linha(banco):
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        await _digitar(piloto, "12 lqdr")
        assert app.query_one("#linha", Input).value == "12 lqdr"
        assert app.is_running
        await piloto.press("escape")
        assert not app.query_one("#linha", Input).display


async def test_erro_aparece_na_previa(banco):
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "10 x 31/02"
        await piloto.pause()
        assert "data impossível" in _previa(app)
        await piloto.press("enter")
        await piloto.pause()
        assert banco.lancamentos_do_mes(Mes(2026, 2)) == []


async def test_excluir_parcela_pergunta_e_padrao_e_todas(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "120 geladeira @nubank 3x"
        await piloto.press("enter")
        await piloto.pause()
        await piloto.press("escape")
        await piloto.press("d")
        await piloto.pause()
        assert isinstance(app.screen, SoEstaOuTodas)
        await piloto.press("enter")
        await piloto.pause()
        assert app.query_one("#vazio", Static).display
    assert banco.lancamentos_do_mes(Mes(2026, 12)) == []
    assert banco.conta_por_nome("nubank") == nubank


async def test_renomear_so_esta(banco):
    app = MoneyApp(banco, hoje=HOJE)
    banco.criar_conta("nubank", "#8a2be2")
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "120 geladeira @nubank 3x"
        await piloto.press("enter")
        await piloto.pause()
        await piloto.press("escape", "r")
        await piloto.pause()
        await piloto.press("s")
        await piloto.pause()
        app.screen.query_one(Input).value = "geladeira 1"
        await piloto.press("enter")
        await piloto.pause()
    assert banco.lancamentos_do_mes(Mes(2026, 11))[0].descricao == "geladeira 1"
    assert banco.lancamentos_do_mes(Mes(2026, 12))[0].descricao == "geladeira"


async def test_excluir_simples_confirma(banco):
    app = MoneyApp(banco, hoje=HOJE)
    banco.criar_conta("nubank", "#8a2be2")
    async with app.run_test() as piloto:
        await piloto.press("l")
        app.query_one("#linha", Input).value = "10 café @nubank"
        await piloto.press("enter")
        await piloto.pause()
        await piloto.press("escape", "d")
        await piloto.pause()
        assert isinstance(app.screen, SimOuNao)
        await piloto.press("escape")
        await piloto.pause()
        assert len(banco.lancamentos_do_mes(Mes(2026, 11))) == 1
        await piloto.press("d", "enter")
        await piloto.pause()
    assert banco.lancamentos_do_mes(Mes(2026, 11)) == []
