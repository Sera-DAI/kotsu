import datetime as dt
import sqlite3

import pytest

from money_cli.armazenamento import migracoes
from money_cli.armazenamento.banco import Banco, migrar, versao_do_esquema
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import NovoLancamento, Parcela, Tipo
from money_cli.dominio.totais import TotaisMes

NOV = Mes(2026, 11)


def _despesa(valor, conta_id, dia=8, **extra):
    return NovoLancamento(dt.date(2026, 11, dia), "mercado", valor, Tipo.DESPESA, conta_id, **extra)


def test_banco_novo_fica_na_ultima_versao(tmp_path):
    caminho = tmp_path / "dados" / "money.sqlite"
    b = Banco.abrir(caminho)
    assert b.versao == len(migracoes.carregar()) >= 1
    b.fechar()
    assert caminho.exists()
    # Abrir de novo não reaplica nada e não faz cópia.
    Banco.abrir(caminho).fechar()
    assert list(tmp_path.joinpath("dados").glob("*.antes-*")) == []


def test_copia_antes_de_migrar_banco_com_dados(tmp_path):
    caminho = tmp_path / "money.sqlite"
    b = Banco.abrir(caminho)
    b.inserir_lancamentos([_despesa(8990, b.criar_conta("Nubank", "#8a2be2").id)])
    b.fechar()

    reais = migracoes.carregar()
    nova = migracoes.Migracao(len(reais) + 1, "teste.sql", "ALTER TABLE conta ADD extra TEXT;")
    conexao = sqlite3.connect(caminho, isolation_level=None)
    assert migrar(conexao, caminho, [*reais, nova]) == nova.versao
    conexao.close()

    copia = tmp_path / f"money.antes-v{nova.versao}.sqlite"
    assert copia.exists()
    antiga = sqlite3.connect(copia)
    assert versao_do_esquema(antiga) == len(reais)
    assert antiga.execute("SELECT count(*) FROM lancamento").fetchone()[0] == 1
    antiga.close()


def test_migracao_que_falha_nao_deixa_rastro(tmp_path):
    caminho = tmp_path / "money.sqlite"
    Banco.abrir(caminho).fechar()
    reais = migracoes.carregar()
    quebrada = migracoes.Migracao(
        len(reais) + 1,
        "quebrada.sql",
        "ALTER TABLE conta ADD extra TEXT;\nSELECT * FROM tabela_que_nao_existe;",
    )
    conexao = sqlite3.connect(caminho, isolation_level=None)
    with pytest.raises(sqlite3.OperationalError):
        migrar(conexao, caminho, [*reais, quebrada])
    assert versao_do_esquema(conexao) == len(reais)
    colunas = [c[1] for c in conexao.execute("PRAGMA table_info(conta)")]
    assert "extra" not in colunas
    conexao.close()


def test_banco_mais_novo_que_o_app_recusa_abrir(tmp_path):
    caminho = tmp_path / "money.sqlite"
    conexao = sqlite3.connect(caminho)
    conexao.execute("PRAGMA user_version = 999")
    conexao.close()
    with pytest.raises(RuntimeError, match="999"):
        Banco.abrir(caminho)


def test_parcelas_sao_gravadas_todas_ou_nenhuma(banco):
    nubank = banco.criar_conta("Nubank", "#8a2be2")
    grupo = banco.novo_grupo_parcela()
    boas = [_despesa(12000, nubank.id, parcela=Parcela(grupo, n, 3)) for n in (1, 2)]
    ruim = _despesa(12000, 999, parcela=Parcela(grupo, 3, 3))  # conta inexistente
    with pytest.raises(sqlite3.IntegrityError):
        banco.inserir_lancamentos([*boas, ruim])
    assert banco.lancamentos_do_mes(NOV) == []


def test_transacao_desfaz_em_erro_qualquer(banco):
    with pytest.raises(KeyError):
        with banco.transacao() as c:
            c.execute("INSERT INTO categoria (nome) VALUES ('casa')")
            raise KeyError("boom")
    assert banco.listar_categorias() == []


@pytest.mark.parametrize(
    ("data", "valor", "conta"),
    [
        ("2026-11-08", 89.9, 1),  # valor não inteiro
        ("08/11/2026", 100, 1),  # data fora do formato ISO
        ("2026-11-08", 100, None),  # sem conta (D21)
        ("2026-11-08", 100, 999),  # conta inexistente
    ],
)
def test_esquema_recusa_lancamento_errado(banco, data, valor, conta):
    banco.criar_conta("Nubank", "#8a2be2")
    with pytest.raises(sqlite3.IntegrityError), banco.transacao() as c:
        c.execute(
            "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id)"
            " VALUES (?, 'x', ?, 'despesa', ?)",
            (data, valor, conta),
        )
    assert banco.lancamentos_do_mes(NOV) == []


def test_esquema_aceita_lancamento_certo_e_conta_unica(banco):
    banco.criar_conta("Nubank", "#8a2be2")
    with banco.transacao() as c:
        c.execute(
            "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id)"
            " VALUES ('2026-11-08', 'x', 100, 'despesa', 1)"
        )
    assert len(banco.lancamentos_do_mes(NOV)) == 1
    with pytest.raises(sqlite3.IntegrityError):
        banco.criar_conta("nubank", "#000000")  # nome único sem diferenciar maiúsculas


def test_totais_e_lista_do_mes(banco):
    nubank = banco.criar_conta("Nubank", "#8a2be2")
    casa = banco.criar_categoria("casa")
    banco.inserir_lancamentos(
        [
            NovoLancamento(dt.date(2026, 11, 5), "salário", 350000, Tipo.RECEITA, nubank.id),
            _despesa(8990, nubank.id, dia=1, categoria_id=casa.id),
            _despesa(5000, nubank.id, dia=30),
            NovoLancamento(dt.date(2026, 10, 31), "outubro", 777, Tipo.DESPESA, nubank.id),
            NovoLancamento(dt.date(2026, 12, 1), "dezembro", 777, Tipo.DESPESA, nubank.id),
        ]
    )
    assert banco.totais_do_mes(NOV) == TotaisMes(350000, 13990, 3)
    datas = [x.data.day for x in banco.lancamentos_do_mes(NOV)]
    assert datas == [30, 5, 1]
    assert [x.data.day for x in banco.lancamentos_do_mes(NOV, limite=1, desde=1)] == [5]
    assert banco.totais_do_mes(Mes(2027, 1)) == TotaisMes()


def test_mes_usa_o_indice_de_data(banco):
    plano = banco._conexao.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM lancamento WHERE data >= ? AND data < ?",
        ("2026-11-01", "2026-12-01"),
    ).fetchall()
    assert any("lancamento_data" in linha[-1] for linha in plano)
