"""Temas (D37): troca com `t`, tema.toml, padrão e cores de valor."""

import datetime as dt

from textual.widgets import Static

from money_cli.armazenamento import preferencias
from money_cli.dominio.tipos import NovoLancamento, Tipo
from money_cli.tela import cores
from money_cli.tela.app import MoneyApp
from money_cli.tela.temas import ALGODAO_CLARO, ALGODAO_NOITE, TEMAS, tema_por_nome

HOJE = dt.date(2026, 11, 8)


def _com_dados(banco):
    conta = banco.criar_conta("nubank", "#8a2be2")
    banco.criar_conta("inter", "#1f8fff")
    banco.inserir_lancamentos(
        [NovoLancamento(dt.date(2026, 11, 7), "mercado", 8990, Tipo.DESPESA, conta.id)]
    )


def test_tema_desconhecido_ou_ausente_volta_ao_padrao():
    assert tema_por_nome(None) is ALGODAO_NOITE
    assert tema_por_nome("nao-existe") is ALGODAO_NOITE
    assert tema_por_nome("algodao-claro") is ALGODAO_CLARO


def test_preferencias_gravam_e_leem(tmp_path):
    assert preferencias.ler_tema(tmp_path) is None
    assert preferencias.gravar_tema(tmp_path, "algodao-claro")
    assert preferencias.ler_tema(tmp_path) == "algodao-claro"
    assert not list(tmp_path.glob("*.tmp"))


def test_arquivo_estragado_nao_impede_abrir(tmp_path):
    (tmp_path / preferencias.NOME_ARQUIVO).write_text("tema = [", encoding="utf-8")
    assert preferencias.ler_tema(tmp_path) is None
    (tmp_path / preferencias.NOME_ARQUIVO).write_text("tema = 3\n", encoding="utf-8")
    assert preferencias.ler_tema(tmp_path) is None


def test_pasta_impossivel_nao_levanta(tmp_path):
    arquivo = tmp_path / "arquivo"
    arquivo.write_text("x")
    assert not preferencias.gravar_tema(arquivo / "dentro", "algodao-claro")


async def test_abre_no_tema_noite_e_t_alterna_e_grava(banco, tmp_path):
    _com_dados(banco)
    app = MoneyApp(banco, hoje=HOJE, pasta_tema=tmp_path)
    async with app.run_test() as pilot:
        assert app.theme == "algodao-noite" and cores.RECEITA == ALGODAO_NOITE.receita
        await pilot.press("t")
        assert app.theme == "algodao-claro" and cores.DESPESA == ALGODAO_CLARO.despesa
        assert preferencias.ler_tema(tmp_path) == "algodao-claro"
        await pilot.press("t")
        assert app.theme == "algodao-noite"
        assert preferencias.ler_tema(tmp_path) == "algodao-noite"


async def test_lembra_o_tema_ao_abrir_de_novo(banco, tmp_path):
    preferencias.gravar_tema(tmp_path, "algodao-claro")
    app = MoneyApp(banco, hoje=HOJE, pasta_tema=tmp_path)
    async with app.run_test():
        assert app.theme == "algodao-claro"


async def test_sem_pasta_troca_mas_nao_grava(banco, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as pilot:
        await pilot.press("t")
        assert app.theme == "algodao-claro"
    assert not list(tmp_path.iterdir())


async def test_troca_nao_perde_o_conteudo_e_t_nao_atrapalha_a_linha(banco, tmp_path):
    _com_dados(banco)
    app = MoneyApp(banco, hoje=HOJE, pasta_tema=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("t")
        topo = str(app.query_one("#topo", Static).render())
        contas = str(app.query_one("#contas", Static).render())
        assert "89,90" in topo and "Novembro de 2026" in topo
        assert "zerada" in contas and "inter" in contas
        await pilot.press("l")  # com a linha aberta, "t" é texto, não troca de tema
        await pilot.press("t")
        assert app.theme == "algodao-claro"


def test_todo_tema_tem_cores_distintas_e_nome_unico():
    assert len({t.nome for t in TEMAS}) == len(TEMAS)
    for t in TEMAS:
        assert t.receita != t.despesa and t.fundo != t.texto
