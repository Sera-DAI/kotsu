"""Troca de dados entre aparelhos (D39): identidade, mesclagem, arquivo, conferência."""

import datetime as dt
import json
import random
import sqlite3

import pytest

import gerar_vetores
from money_cli.__main__ import main
from money_cli.armazenamento import migracoes, trava, troca
from money_cli.armazenamento.banco import Banco, migrar
from money_cli.dominio import mescla
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import Alcance, NovoLancamento, Parcela, Tipo
from money_cli.tela.app import MoneyApp

NOV = Mes(2026, 11)


class Relogio:
    """Relógio de parede que os testes adiantam (ou atrasam) à mão."""

    def __init__(self, ms: int) -> None:
        self.ms = ms

    def __call__(self) -> int:
        self.ms += 1
        return self.ms


def _banco(inicio_ms: int) -> Banco:
    banco = Banco.em_memoria()
    banco.agora_ms = Relogio(inicio_ms)
    return banco


def _lancar(banco, descricao, valor=1000, conta="nubank", dia=8, categoria=None, **outros):
    conta_ = banco.conta_por_nome(conta) or banco.criar_conta(conta, "#8a2be2")
    categoria_ = None
    if categoria:
        categoria_ = banco.categoria_por_nome(categoria) or banco.criar_categoria(categoria)
    novo = NovoLancamento(
        dt.date(2026, 11, dia),
        descricao,
        valor,
        Tipo.DESPESA,
        conta_.id,
        categoria_.id if categoria_ else None,
        **outros,
    )
    return banco.inserir_lancamentos([novo])[0]


def _trocar(origem: Banco, destino: Banco, tmp_path) -> mescla.Resumo:
    arquivo = tmp_path / "troca.json"
    troca.exportar(origem, arquivo)
    return troca.importar(destino, arquivo)


def _descricoes(banco, mes=NOV) -> list[str]:
    return sorted(x.descricao for x in banco.lancamentos_do_mes(mes))


@pytest.fixture
def pc():
    banco = _banco(1_000_000)
    yield banco
    banco.fechar()


@pytest.fixture
def celular():
    banco = _banco(2_000_000)
    yield banco
    banco.fechar()


# --- casos compartilhados com o Android --------------------------------------------


def test_vetores_no_disco_batem_com_o_gerador():
    assert gerar_vetores.desatualizados() == []


@pytest.mark.parametrize("caso", gerar_vetores.gerar()["mescla.json"], ids=lambda c: c["nome"])
def test_mesclar_e_comutativo_e_pode_repetir(caso):
    a, b, esperado = caso["a"], caso["b"], caso["esperado"]
    assert mescla.mesclar(a, b) == esperado
    assert mescla.mesclar(b, a) == esperado
    assert mescla.mesclar(esperado, a) == esperado
    assert mescla.mesclar(b, esperado) == esperado
    assert mescla.codigo(esperado) == caso["codigo_esperado"]


def test_casos_escolhidos_dao_o_resultado_escrito_a_mao():
    """As saídas dos vetores vêm do próprio código; estes conferem as regras por fora."""
    casos = {c["nome"]: c["esperado"] for c in gerar_vetores.gerar()["mescla.json"]}

    editado = casos["mesmo lançamento editado nos dois lados: vale o carimbo maior, inteiro"]
    assert [(x["descricao"], x["valor"]) for x in editado["lancamentos"]] == [("padaria", 1500)]

    excluido = casos["excluído em um lado depois da última edição do outro: sai"]
    assert excluido["lancamentos"] == []
    assert [x["uid"] for x in excluido["lapides"]] == ["l-1"]

    voltou = casos["editado em um lado depois de excluído no outro: volta"]
    assert [x["descricao"] for x in voltou["lancamentos"]] == ["voltou"]

    conta = casos[
        "mesma conta criada nos dois lados: vira uma, com o menor uid e o conteúdo mais novo"
    ]
    assert [(c["uid"], c["nome"], c["cor"]) for c in conta["contas"]] == [
        ("c-aa", "ITAÚ", "#0000ff")
    ]
    assert {x["conta"] for x in conta["lancamentos"]} == {"c-aa"}

    serie = casos["série: os dois lados geraram o mesmo mês; um gerou mais longe"]
    assert [x["uid"] for x in serie["lancamentos"]] == ["l-1", "s-1-2026-12", "s-1-2027-01"]
    assert serie["recorrencias"][0]["gerada_ate"] == "2027-01-01"

    mes_excluido = casos[
        "série: mês gerado em um lado e excluído (só este) no outro continua excluído"
    ]
    assert mes_excluido["lancamentos"] == []

    encerrada = casos["série: encerrada em um lado, modelo mais velho no outro"]
    assert encerrada["recorrencias"][0]["encerrada"] is True
    assert encerrada["recorrencias"][0]["gerada_ate"] == "2027-03-01"


def _estado_aleatorio(sorteio: random.Random) -> dict:
    """Estado pequeno e válido. Como no app, nome não muda e carimbo igual = conteúdo igual."""
    g = gerar_vetores
    nomes = {"c1": "nu", "c2": "NU", "c3": "itaú", "c4": "x", "g1": "casa", "g2": "CASA", "g3": "y"}

    def carimbo() -> str:
        replica = sorteio.choice(["aaaaaaaa", "bbbbbbbb", "cccccccc"])
        return g._c(sorteio.randint(1, 6), replica, sorteio.randint(0, 1))

    def fixo(*chave) -> random.Random:
        return random.Random(repr(chave))

    def sem_repetir(uids, criar):
        itens, usados = [], set()
        for uid in uids:
            if nomes[uid].casefold() not in usados:
                usados.add(nomes[uid].casefold())
                itens.append(criar(uid, carimbo()))
        return itens

    contas = sem_repetir(
        sorteio.sample(["c1", "c2", "c3", "c4"], sorteio.randint(1, 3)),
        lambda uid, em: g.conta(uid, nomes[uid], em, cor=fixo(uid, em).choice(["#1", "#2"])),
    )
    categorias = sem_repetir(
        sorteio.sample(["g1", "g2", "g3"], sorteio.randint(0, 2)),
        lambda uid, em: g.categoria(uid, nomes[uid], em, fixo(uid, em).random() < 0.5),
    )
    uids_conta = [c["uid"] for c in contas]
    uids_categoria = [c["uid"] for c in categorias] + [None]
    series = []
    for grupo in sorteio.sample(["s1", "s2"], sorteio.randint(0, 2)):
        em = carimbo()
        series.append(
            g.serie(
                grupo,
                em,
                conta=fixo(grupo, em, "c").choice(["c1", "c2", "c3", "c4"]),
                categoria=None,
                gerada_ate=sorteio.choice(["2026-11-01", "2027-01-01"]),
                encerrada=fixo(grupo, em).random() < 0.3,
            )
        )
    series = [s for s in series if s["conta"] in uids_conta]
    grupos = [s["grupo"] for s in series] + [None]
    lancamentos = []
    for uid in sorteio.sample(["l1", "l2", "l3", "l4"], sorteio.randint(0, 4)):
        em = carimbo()
        lancamentos.append(
            g.lanc(
                uid,
                em,
                valor=fixo(uid, em).choice([1, 2, 3]),
                gerado=fixo(uid, em).random() < 0.3,
                conta=sorteio.choice(uids_conta),
                categoria=sorteio.choice(uids_categoria),
                recorrencia=sorteio.choice(grupos),
            )
        )
    lapides = [
        g.lapide(uid, carimbo())
        for uid in sorteio.sample(["l1", "l2", "l3", "l4"], sorteio.randint(0, 2))
    ]
    return mescla.validar(
        g.estado(
            contas=contas,
            categorias=categorias,
            recorrencias=series,
            lancamentos=lancamentos,
            lapides=lapides,
        )
    )


def test_mesclar_converge_em_qualquer_ordem():
    """Três aparelhos: tanto faz quem junta com quem primeiro."""
    sorteio = random.Random(39)
    for _ in range(1500):
        a, b, c = (_estado_aleatorio(sorteio) for _ in range(3))
        ab = mescla.mesclar(a, b)
        assert ab == mescla.mesclar(b, a)
        assert mescla.mesclar(ab, a) == ab
        assert mescla.mesclar(ab, c) == mescla.mesclar(a, mescla.mesclar(b, c))


@pytest.mark.parametrize("caso", gerar_vetores.gerar()["invalidos.json"], ids=lambda c: c["nome"])
def test_arquivo_invalido_e_recusado(caso):
    with pytest.raises(mescla.ErroDeTroca) as erro:
        mescla.validar(caso["arquivo"])
    assert str(erro.value) == caso["erro"]


def test_carimbo_nunca_anda_para_tras():
    ultimo = mescla.CARIMBO_ZERO
    for agora in (50, 50, 49, 10, 51, 51):
        novo = mescla.carimbo(agora, ultimo, "ab12cd34")
        assert novo > ultimo
        ultimo = novo
    cheio = "0000000000050-9999-ab12cd34"
    assert mescla.carimbo(50, cheio, "ab12cd34") == "0000000000051-0000-ab12cd34"


# --- banco: identidade e carimbos ---------------------------------------------------


def test_migracao_0003_da_identidade_a_quem_ja_existia(tmp_path):
    caminho = tmp_path / "money.sqlite"
    conexao = sqlite3.connect(caminho, isolation_level=None)
    migrar(conexao, caminho, migracoes.carregar()[:2])
    conexao.execute("INSERT INTO conta (nome, cor) VALUES ('a', '#fff'), ('b', '#000')")
    conexao.execute("INSERT INTO categoria (nome) VALUES ('casa')")
    conexao.executemany(
        "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id)"
        " VALUES ('2026-11-01', ?, 100, 'despesa', 1, 1)",
        [("x",), ("y",), ("z",)],
    )
    conexao.close()

    banco = Banco.abrir(caminho)
    assert banco.versao == 3
    assert (tmp_path / "money.antes-v3.sqlite").exists()
    assert trava.conflitos(tmp_path, "money.sqlite") == []
    estado = mescla.validar({"app": "kotsu", "formato": 1, **troca.ler_estado(banco)})
    assert len({x["uid"] for x in estado["lancamentos"]}) == 3
    assert len({c["uid"] for c in estado["contas"]}) == 2
    assert {x["alterado_em"] for x in estado["lancamentos"]} == {mescla.CARIMBO_ZERO}
    assert len(banco.replica) == 8
    assert _descricoes(banco) == ["x", "y", "z"]
    # Quem insere por fora do Banco (sem uid) também ganha identidade.
    with banco.transacao() as c:
        c.execute(
            "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id)"
            " VALUES ('2026-11-02', 'w', 100, 'despesa', 1)"
        )
    assert len({x["uid"] for x in troca.ler_estado(banco)["lancamentos"]}) == 4
    banco.fechar()


def test_cada_alteracao_ganha_carimbo_maior_mesmo_com_relogio_atrasado(pc):
    id_ = _lancar(pc, "padaria")
    primeiro = troca.ler_estado(pc)["lancamentos"][0]["alterado_em"]
    pc.agora_ms = Relogio(5)  # o relógio do computador voltou no tempo
    pc.renomear(id_, "padaria do zé")
    depois = troca.ler_estado(pc)["lancamentos"][0]
    assert depois["alterado_em"] > primeiro
    assert depois["alterado_em"].endswith(pc.replica)


def test_excluir_deixa_lapide_de_cada_parcela(pc):
    conta = pc.criar_conta("nubank", "#8a2be2")
    grupo = pc.novo_grupo_parcela()
    ids = pc.inserir_lancamentos(
        [
            NovoLancamento(
                dt.date(2026, 11 + i, 10),
                "tv",
                100,
                Tipo.DESPESA,
                conta.id,
                None,
                Parcela(grupo, i + 1, 2),
            )
            for i in range(2)
        ]
    )
    uids = {x["uid"] for x in troca.ler_estado(pc)["lancamentos"]}
    assert pc.excluir(ids[0], Alcance.TODAS) == 2
    estado = troca.ler_estado(pc)
    assert estado["lancamentos"] == []
    assert {x["uid"] for x in estado["lapides"]} == uids


# --- dois aparelhos -----------------------------------------------------------------


def test_primeira_importacao_copia_tudo_e_os_codigos_batem(pc, celular, tmp_path):
    _lancar(pc, "padaria", categoria="casa")
    _lancar(pc, "mercado", conta="itaú")
    resumo = _trocar(pc, celular, tmp_path)
    assert (resumo.entraram, resumo.mudaram, resumo.sairam) == (2, 0, 0)
    assert _descricoes(celular) == ["mercado", "padaria"]
    assert [c.nome for c in celular.listar_contas()] == ["itaú", "nubank"]
    assert troca.codigo(celular) == troca.codigo(pc)
    assert celular.replica != pc.replica
    assert _trocar(pc, celular, tmp_path).nada  # repetir não muda nada


def test_lancamentos_dos_dois_lados_se_juntam(pc, celular, tmp_path):
    padaria = _lancar(pc, "padaria")
    _lancar(pc, "luz")
    _trocar(pc, celular, tmp_path)

    # Sem se falar: o celular lança, exclui e cria uma conta; o PC renomeia e cria a mesma conta.
    _lancar(celular, "uber", conta="Itaú")
    luz = next(x for x in celular.lancamentos_do_mes(NOV) if x.descricao == "luz")
    celular.excluir(luz.id)
    pc.renomear(padaria, "padaria do zé")
    _lancar(pc, "mercado", conta="itaú")
    assert troca.codigo(pc) != troca.codigo(celular)

    _trocar(celular, pc, tmp_path)
    _trocar(pc, celular, tmp_path)

    esperado = ["mercado", "padaria do zé", "uber"]
    assert _descricoes(pc) == esperado
    assert _descricoes(celular) == esperado
    assert troca.codigo(pc) == troca.codigo(celular)
    assert troca.ler_estado(pc) == troca.ler_estado(celular)
    # "itaú" e "Itaú" viraram uma conta só, com os lançamentos dos dois lados.
    for banco in (pc, celular):
        contas = [c for c in banco.listar_contas() if c.nome.casefold() == "itaú"]
        assert len(contas) == 1
        na_conta = [x for x in banco.lancamentos_do_mes(NOV) if x.conta_id == contas[0].id]
        assert sorted(x.descricao for x in na_conta) == ["mercado", "uber"]


def test_edicao_depois_de_importar_vence_o_que_veio(pc, celular, tmp_path):
    """O relógio do celular está atrasado, mas a edição feita depois de importar vale."""
    celular.agora_ms = Relogio(10)
    id_pc = _lancar(pc, "padaria")
    pc.renomear(id_pc, "padaria nova")
    _trocar(pc, celular, tmp_path)
    no_celular = celular.lancamentos_do_mes(NOV)[0]
    celular.renomear(no_celular.id, "padoca")
    _trocar(celular, pc, tmp_path)
    assert _descricoes(pc) == ["padoca"]


def test_serie_nao_duplica_e_mes_excluido_nao_volta(pc, celular, tmp_path):
    conta = pc.criar_conta("nubank", "#8a2be2")
    aluguel = pc.criar_categoria("aluguel", recorrente=True)
    pc.inserir_lancamentos(
        [
            NovoLancamento(
                dt.date(2026, 11, 5),
                "aluguel",
                100000,
                Tipo.DESPESA,
                conta.id,
                aluguel.id,
                grupo_recorrencia=pc.novo_grupo_parcela(),
            )
        ]
    )
    _trocar(pc, celular, tmp_path)
    codigo = troca.codigo(pc)

    # Cada um navega até um mês diferente: geram os mesmos registros, e o código não muda.
    pc.estender_recorrencias(Mes(2027, 1))
    celular.estender_recorrencias(Mes(2027, 3))
    assert troca.codigo(pc) == codigo == troca.codigo(celular)

    # O celular exclui dezembro ("só este") e edita janeiro; o PC nem sabe.
    dezembro = celular.lancamentos_do_mes(Mes(2026, 12))[0]
    celular.excluir(dezembro.id, Alcance.SO_ESTA)
    janeiro = celular.lancamentos_do_mes(Mes(2027, 1))[0]
    celular.editar(
        janeiro.id,
        NovoLancamento(
            janeiro.data, "aluguel", 110000, Tipo.DESPESA, janeiro.conta_id, janeiro.categoria_id
        ),
        Alcance.SO_ESTA,
    )
    assert troca.codigo(pc) != troca.codigo(celular)

    _trocar(celular, pc, tmp_path)
    _trocar(pc, celular, tmp_path)
    for banco in (pc, celular):
        banco.estender_recorrencias(Mes(2027, 4))  # navegar de novo não ressuscita nada
        assert banco.lancamentos_do_mes(Mes(2026, 12)) == []
        assert [x.valor for x in banco.lancamentos_do_mes(Mes(2027, 1))] == [110000]
        for mes in (Mes(2027, 2), Mes(2027, 3), Mes(2027, 4)):
            assert [x.valor for x in banco.lancamentos_do_mes(mes)] == [100000]
    assert troca.codigo(pc) == troca.codigo(celular)


def test_serie_editada_em_um_lado_vale_para_os_meses_que_o_outro_ainda_vai_gerar(
    pc, celular, tmp_path
):
    conta = pc.criar_conta("nubank", "#8a2be2")
    luz = pc.criar_categoria("luz", recorrente=True)
    primeiro = pc.inserir_lancamentos(
        [
            NovoLancamento(
                dt.date(2026, 11, 31 - 1),
                "luz",
                20000,
                Tipo.DESPESA,
                conta.id,
                luz.id,
                grupo_recorrencia=pc.novo_grupo_parcela(),
            )
        ]
    )[0]
    _trocar(pc, celular, tmp_path)
    celular.estender_recorrencias(Mes(2026, 12))  # gera dezembro com o valor antigo
    item = pc.lancamento(primeiro)
    pc.editar(
        primeiro,
        NovoLancamento(item.data, "luz", 25000, Tipo.DESPESA, conta.id, luz.id),
        Alcance.PROXIMAS,
    )
    pc.estender_recorrencias(Mes(2026, 12))  # gera dezembro com o valor novo

    _trocar(pc, celular, tmp_path)
    _trocar(celular, pc, tmp_path)
    for banco in (pc, celular):
        banco.estender_recorrencias(Mes(2027, 1))
        for mes in (NOV, Mes(2026, 12), Mes(2027, 1)):
            assert [x.valor for x in banco.lancamentos_do_mes(mes)] == [25000]
    assert troca.ler_estado(pc) == troca.ler_estado(celular)


def test_importar_guarda_copia_antes_e_arquivo_ruim_nao_muda_nada(tmp_path, celular):
    pasta = tmp_path / "pc"
    pc = Banco.abrir(pasta / "money.sqlite")
    _lancar(pc, "padaria")
    antes = troca.ler_estado(pc)

    ruim = tmp_path / "ruim.json"
    ruim.write_text('{"app": "kotsu", "formato": 1, "contas": "não"}', encoding="utf-8")
    with pytest.raises(mescla.ErroDeTroca):
        troca.importar(pc, ruim)
    with pytest.raises(mescla.ErroDeTroca):
        troca.importar(pc, tmp_path / "não-existe.json")
    assert troca.ler_estado(pc) == antes
    assert not (pasta / "backups").exists()

    _lancar(celular, "uber")
    resumo = _trocar(celular, pc, tmp_path)
    assert resumo.entraram == 1
    copia = pasta / "backups" / "money.antes-da-troca.sqlite"
    assert copia.exists()
    assert trava.conflitos(pasta, "money.sqlite") == []  # a cópia não parece conflito do Drive
    anterior = Banco.abrir(copia)
    assert _descricoes(anterior) == ["padaria"]
    anterior.fechar()
    pc.fechar()


def test_arquivo_exportado_e_json_legivel_e_valido(pc, tmp_path):
    _lancar(pc, "pão de ló", categoria="alimentação")
    arquivo = tmp_path / "sub" / "kotsu-pc.json"
    codigo = troca.exportar(pc, arquivo, dt.datetime(2026, 11, 11, 10, 0, 0))
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert dados["app"] == "kotsu" and dados["formato"] == 1
    assert dados["replica"] == pc.replica
    assert dados["exportado_em"] == "2026-11-11T10:00:00"
    assert dados["conferencia"] == codigo == mescla.codigo(dados)
    assert "alimentação" in arquivo.read_text(encoding="utf-8")  # sem escapar acentos
    assert list(arquivo.parent.iterdir()) == [arquivo]  # nenhum temporário sobrou
    mescla.validar(dados)


def test_comparar_lista_o_que_falta_em_cada_lado(pc, celular, tmp_path):
    padaria = _lancar(pc, "padaria")
    _trocar(pc, celular, tmp_path)
    _lancar(pc, "mercado")
    _lancar(celular, "uber")
    pc.renomear(padaria, "padoca")
    arquivo = tmp_path / "celular.json"
    troca.exportar(celular, arquivo)
    diferencas = troca.comparar(pc, arquivo)
    assert not diferencas.iguais
    assert [x["descricao"] for x in diferencas.so_aqui] == ["mercado"]
    assert [x["descricao"] for x in diferencas.so_la] == ["uber"]
    assert [(a["descricao"], b["descricao"]) for a, b in diferencas.diferentes] == [
        ("padoca", "padaria")
    ]
    aqui = troca.ler_estado(pc)
    assert mescla.descrever(diferencas.so_aqui[0], aqui) == "08/11/2026 -10,00 mercado @nubank"


# --- linha de comando e tela ---------------------------------------------------------


def test_comandos_exportar_importar_conferir(tmp_path, capsys):
    pc, celular = tmp_path / "pc", tmp_path / "celular"
    banco = Banco.abrir(pc / "money.sqlite")
    _lancar(banco, "padaria")
    banco.fechar()
    arquivo = tmp_path / "pc.json"

    assert main(["--dados", str(pc), "--exportar", str(arquivo)]) == 0
    codigo = json.loads(arquivo.read_text(encoding="utf-8"))["conferencia"]
    assert codigo in capsys.readouterr().out

    assert main(["--dados", str(celular), "--importar", str(arquivo)]) == 0
    saida = capsys.readouterr().out
    assert "1 entraram, 0 mudaram, 0 saíram" in saida and codigo in saida

    assert main(["--dados", str(celular), "--conferir"]) == 0
    assert codigo in capsys.readouterr().out
    assert main(["--dados", str(celular), "--conferir", str(arquivo)]) == 0
    assert "Iguais" in capsys.readouterr().out

    banco = Banco.abrir(celular / "money.sqlite")
    _lancar(banco, "uber")
    banco.fechar()
    assert main(["--dados", str(celular), "--conferir", str(arquivo)]) == 2
    saida = capsys.readouterr().out
    assert "Só aqui (1):" in saida and "uber" in saida

    assert main(["--dados", str(pc), "--importar", str(tmp_path / "nada.json")]) == 1
    assert "Não deu certo" in capsys.readouterr().err
    assert not (pc / trava.NOME_TRAVA).exists()  # a trava é liberada ao sair


def test_comandos_de_troca_respeitam_a_trava(tmp_path, capsys, monkeypatch):
    pasta = tmp_path / "pc"
    pasta.mkdir()
    (pasta / trava.NOME_TRAVA).write_text(
        json.dumps({"maquina": "NOTEBOOK", "pid": 1, "desde": "10/11/2026 22:00"}),
        encoding="utf-8",
    )
    assert main(["--dados", str(pasta), "--exportar", str(tmp_path / "x.json")]) == 1
    assert "NOTEBOOK" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


async def test_tecla_v_mostra_o_codigo_de_conferencia(banco):
    _lancar(banco, "padaria")
    app = MoneyApp(banco, hoje=dt.date(2026, 11, 11))
    async with app.run_test() as piloto:
        await piloto.press("v")
        await piloto.pause()
        avisos = [aviso.message for aviso in app._notifications]
    assert avisos == [f"Código de conferência: {troca.codigo(banco)}"]
