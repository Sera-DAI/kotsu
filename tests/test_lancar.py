"""Gravação da linha rápida, parcelas e "só esta ou todas?" (critérios 3, 4 e 10)."""

import datetime as dt
import sqlite3

import pytest

from money_cli.dominio import parcelas
from money_cli.dominio.linha import interpretar
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import Alcance, NovoLancamento, Parcela, Tipo

HOJE = dt.date(2026, 11, 8)


def _salvar(banco, texto, conta_id, categoria_id=None):
    linha = interpretar(texto, HOJE)
    grupo = banco.novo_grupo_parcela() if linha.parcelas > 1 else None
    return banco.inserir_lancamentos(parcelas.gerar(linha, conta_id, categoria_id, grupo))


def test_dez_parcelas_uma_por_mes(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    _salvar(banco, "120 10x", nubank.id)
    for i in range(10):
        mes = Mes(2026, 11).somar(i)
        (item,) = banco.lancamentos_do_mes(mes)
        assert (item.valor, item.tipo, item.parcela.rotulo) == (12000, Tipo.DESPESA, f"{i + 1}/10")
        assert banco.totais_do_mes(mes).despesas == 12000
    assert banco.lancamentos_do_mes(Mes(2027, 9)) == []


def test_parcelas_entram_todas_ou_nenhuma(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    linha = interpretar("120 geladeira 3x", HOJE)
    novos = parcelas.gerar(linha, nubank.id, None, "g")
    novos[-1] = NovoLancamento(HOJE, "x", 1, Tipo.DESPESA, 999)  # conta inexistente
    with pytest.raises(sqlite3.IntegrityError):
        banco.inserir_lancamentos(novos)
    assert banco.lancamentos_do_mes(Mes(2026, 11)) == []


def test_busca_por_nome_ignora_maiusculas_e_acentuadas(banco):
    itau = banco.criar_conta("Itaú", "#ff7a00")
    casa = banco.criar_categoria("Casa")
    assert banco.conta_por_nome("ITAÚ") == itau
    assert banco.conta_por_nome("nubank") is None
    assert banco.categoria_por_nome(" casa ") == casa


@pytest.fixture
def compra(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    ids = _salvar(banco, "120 geladeira 3x", nubank.id)
    avulso = _salvar(banco, "10 café", nubank.id)[0]
    return ids, avulso


def test_excluir_parcela_por_padrao_exclui_todas(banco, compra):
    ids, avulso = compra
    assert banco.excluir(ids[1]) == 3
    assert all(banco.lancamento(i) is None for i in ids)
    assert banco.lancamento(avulso) is not None


def test_excluir_so_esta(banco, compra):
    ids, _ = compra
    assert banco.excluir(ids[1], Alcance.SO_ESTA) == 1
    assert banco.lancamento(ids[0]) and banco.lancamento(ids[2])


def test_renomear_todas_ou_so_esta(banco, compra):
    ids, avulso = compra
    assert banco.renomear(ids[0], "geladeira brastemp") == 3
    assert {banco.lancamento(i).descricao for i in ids} == {"geladeira brastemp"}
    assert banco.renomear(ids[2], "última", Alcance.SO_ESTA) == 1
    assert banco.lancamento(ids[2]).descricao == "última"
    assert banco.lancamento(ids[1]).descricao == "geladeira brastemp"
    assert banco.lancamento(avulso).descricao == "café"


def test_lancamento_simples_ignora_alcance(banco, compra):
    _, avulso = compra
    assert banco.excluir(avulso, Alcance.TODAS) == 1


def test_parcela_lida_do_banco(banco):
    nubank = banco.criar_conta("nubank", "#8a2be2")
    (i,) = banco.inserir_lancamentos(
        [NovoLancamento(HOJE, "x", 1, Tipo.DESPESA, nubank.id, parcela=Parcela("g", 2, 5))]
    )
    assert banco.lancamento(i).parcela == Parcela("g", 2, 5)
