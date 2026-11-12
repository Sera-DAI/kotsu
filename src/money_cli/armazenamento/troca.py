"""Arquivo de troca entre aparelhos (D39): exportar, importar (mesclar) e conferir.

Cada aparelho tem o próprio banco. Para juntar os dados, um exporta um arquivo JSON com
tudo o que tem e o outro importa: a mesclagem (`dominio.mescla`) decide registro a registro.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from money_cli.armazenamento.banco import Banco, copiar_banco
from money_cli.dominio import mescla
from money_cli.dominio.mescla import Comparacao, ErroDeTroca, Resumo

NOME_ANTES = "antes-da-troca"

_CAMPOS_SERIE = (
    "grupo",
    "dia",
    "descricao",
    "valor",
    "tipo",
    "conta",
    "categoria",
    "gerada_ate",
    "encerrada",
    "alterado_em",
)
_CAMPOS_LANCAMENTO = (
    "uid",
    "data",
    "descricao",
    "valor",
    "tipo",
    "conta",
    "categoria",
    "recorrencia",
    "gerado",
    "alterado_em",
)


def ler_estado(banco: Banco) -> dict:
    """O conteúdo inteiro do banco, com `uid` no lugar dos ids locais."""
    c = banco.conexao
    contas = [
        {"uid": uid, "nome": nome, "cor": cor, "alterado_em": em}
        for uid, nome, cor, em in c.execute(
            "SELECT uid, nome, cor, alterado_em FROM conta ORDER BY uid"
        )
    ]
    categorias = [
        {"uid": uid, "nome": nome, "recorrente": bool(rec), "alterado_em": em}
        for uid, nome, rec, em in c.execute(
            "SELECT uid, nome, recorrente, alterado_em FROM categoria ORDER BY uid"
        )
    ]
    recorrencias = []
    for linha in c.execute(
        "SELECT r.grupo, r.dia, r.descricao, r.valor, r.tipo, conta.uid, categoria.uid,"
        " r.gerada_ate, r.encerrada, r.alterado_em FROM recorrencia r"
        " JOIN conta ON conta.id = r.conta_id"
        " LEFT JOIN categoria ON categoria.id = r.categoria_id ORDER BY r.grupo"
    ):
        serie = dict(zip(_CAMPOS_SERIE, linha, strict=True))
        serie["encerrada"] = bool(serie["encerrada"])
        recorrencias.append(serie)
    lancamentos = []
    for *comuns, grupo, numero, total in c.execute(
        "SELECT l.uid, l.data, l.descricao, l.valor, l.tipo, conta.uid, categoria.uid,"
        " l.grupo_recorrencia, l.gerado, l.alterado_em,"
        " l.grupo_parcela, l.parcela_numero, l.parcela_total FROM lancamento l"
        " JOIN conta ON conta.id = l.conta_id"
        " LEFT JOIN categoria ON categoria.id = l.categoria_id ORDER BY l.uid"
    ):
        lanc = dict(zip(_CAMPOS_LANCAMENTO, comuns, strict=True))
        lanc["gerado"] = bool(lanc["gerado"])
        lanc["parcela"] = (
            None if grupo is None else {"grupo": grupo, "numero": numero, "total": total}
        )
        lancamentos.append(lanc)
    lapides = [
        {"uid": uid, "excluido_em": em}
        for uid, em in c.execute("SELECT uid, excluido_em FROM lapide ORDER BY uid")
    ]
    return {
        "contas": contas,
        "categorias": categorias,
        "recorrencias": recorrencias,
        "lancamentos": lancamentos,
        "lapides": lapides,
    }


def codigo(banco: Banco) -> str:
    """Código de conferência dos dados deste banco."""
    return mescla.codigo(ler_estado(banco))


def exportar(banco: Banco, destino: Path, agora: dt.datetime | None = None) -> str:
    """Escreve o arquivo de troca em `destino` (troca atômica). Devolve o código."""
    estado = ler_estado(banco)
    conferencia = mescla.codigo(estado)
    arquivo = {
        "app": "kotsu",
        "formato": mescla.FORMATO,
        "replica": banco.replica,
        "exportado_em": (agora or dt.datetime.now()).isoformat(timespec="seconds"),
        "conferencia": conferencia,
        **estado,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(prefix=".troca-", suffix=".tmp", dir=destino.parent)
    temporario = Path(nome)
    try:
        with os.fdopen(descritor, "w", encoding="utf-8") as saida:
            json.dump(arquivo, saida, ensure_ascii=False, separators=(",", ":"))
            saida.flush()
            os.fsync(saida.fileno())
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)
    return conferencia


def ler_arquivo(origem: Path) -> dict:
    """Lê e valida um arquivo de troca. Levanta `ErroDeTroca` com mensagem para a pessoa."""
    try:
        texto = origem.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as erro:
        raise ErroDeTroca(f"não foi possível ler {origem}: {erro}") from None
    try:
        dados = json.loads(texto)
    except ValueError:
        raise ErroDeTroca(f"{origem} não é uma exportação do Kotsu") from None
    return mescla.validar(dados)


def comparar(banco: Banco, origem: Path) -> Comparacao:
    """Diferenças entre este banco e o arquivo de outro aparelho. Não muda nada."""
    return mescla.comparar(ler_estado(banco), ler_arquivo(origem))


def importar(banco: Banco, origem: Path) -> Resumo:
    """Mescla o arquivo de outro aparelho neste banco, numa transação só.

    Antes de mudar qualquer coisa, guarda uma cópia do banco em `backups/` (uma só,
    substituída a cada importação que muda algo).
    """
    remoto = ler_arquivo(origem)
    local = ler_estado(banco)
    novo = mescla.mesclar(local, remoto)
    visto = mescla.maior_carimbo(remoto)
    if novo == local:
        with banco.transacao() as c:
            _avancar_relogio(c, visto)
        return Resumo()
    if banco.caminho is not None:
        pasta = banco.pasta_backups or banco.caminho.parent / "backups"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            copiar_banco(banco.conexao, pasta / f"{banco.caminho.stem}.{NOME_ANTES}.sqlite")
        except (OSError, sqlite3.Error) as erro:
            raise ErroDeTroca(
                f"não foi possível guardar a cópia de segurança em {pasta}: {erro}"
            ) from None
    with banco.transacao() as c:
        _aplicar(c, novo)
        _avancar_relogio(c, visto)
    return mescla.resumir(local, novo)


def _avancar_relogio(c: sqlite3.Connection, visto: str) -> None:
    """O próximo carimbo daqui passa de tudo o que o arquivo trouxe."""
    c.execute(
        "UPDATE meta SET valor = max(valor, ?) WHERE chave = 'relogio'",
        (visto,),
    )


def _aplicar(c: sqlite3.Connection, novo: dict) -> None:
    """Deixa o banco igual ao estado `novo`, preservando os ids locais."""
    contas = _aplicar_nomeados(c, "conta", novo["contas"], ("cor",))
    categorias = _aplicar_nomeados(c, "categoria", novo["categorias"], ("recorrente",))

    for r in novo["recorrencias"]:
        c.execute(
            "INSERT INTO recorrencia (grupo, dia, descricao, valor, tipo, conta_id, categoria_id,"
            " gerada_ate, encerrada, alterado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (grupo) DO UPDATE SET dia = excluded.dia,"
            " descricao = excluded.descricao, valor = excluded.valor, tipo = excluded.tipo,"
            " conta_id = excluded.conta_id, categoria_id = excluded.categoria_id,"
            " gerada_ate = excluded.gerada_ate, encerrada = excluded.encerrada,"
            " alterado_em = excluded.alterado_em",
            (
                r["grupo"],
                r["dia"],
                r["descricao"],
                r["valor"],
                r["tipo"],
                contas[r["conta"]],
                categorias.get(r["categoria"]),
                r["gerada_ate"],
                int(r["encerrada"]),
                r["alterado_em"],
            ),
        )

    locais = {uid for (uid,) in c.execute("SELECT uid FROM lancamento")}
    vivos = {x["uid"] for x in novo["lancamentos"]}
    c.executemany("DELETE FROM lancamento WHERE uid = ?", [(uid,) for uid in locais - vivos])
    for x in novo["lancamentos"]:
        p = x["parcela"] or {}
        valores = (
            x["data"],
            x["descricao"],
            x["valor"],
            x["tipo"],
            contas[x["conta"]],
            categorias.get(x["categoria"]),
            p.get("grupo"),
            p.get("numero"),
            p.get("total"),
            x["recorrencia"],
            int(x["gerado"]),
            x["alterado_em"],
            x["uid"],
        )
        if x["uid"] in locais:
            c.execute(
                "UPDATE lancamento SET data = ?, descricao = ?, valor = ?, tipo = ?, conta_id = ?,"
                " categoria_id = ?, grupo_parcela = ?, parcela_numero = ?, parcela_total = ?,"
                " grupo_recorrencia = ?, gerado = ?, alterado_em = ? WHERE uid = ?",
                valores,
            )
        else:
            c.execute(
                "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id,"
                " grupo_parcela, parcela_numero, parcela_total, grupo_recorrencia, gerado,"
                " alterado_em, uid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                valores,
            )

    c.executemany(
        "INSERT OR REPLACE INTO lapide (uid, excluido_em) VALUES (?, ?)",
        [(x["uid"], x["excluido_em"]) for x in novo["lapides"]],
    )


def _aplicar_nomeados(
    c: sqlite3.Connection, tabela: str, itens: list[dict], campos: tuple[str, ...]
) -> dict[str, int]:
    """Grava contas ou categorias mescladas. Devolve `uid -> id local`.

    A que existe aqui com o mesmo nome e outro `uid` é a mesma: passa a usar o `uid` que a
    mesclagem escolheu, e os lançamentos daqui continuam apontando para ela.
    """
    por_uid, por_nome = {}, {}
    for id_, uid, nome in c.execute(f"SELECT id, uid, nome FROM {tabela}").fetchall():
        por_uid[uid] = id_
        por_nome[mescla.chave_do_nome(nome)] = id_
    ids = {}
    atribuicoes = ", ".join(f"{campo} = ?" for campo in campos)
    for item in itens:
        valores = [int(v) if isinstance(v, bool) else v for v in (item[k] for k in campos)]
        id_ = por_uid.get(item["uid"]) or por_nome.get(mescla.chave_do_nome(item["nome"]))
        if id_ is None:
            id_ = c.execute(
                f"INSERT INTO {tabela} (uid, nome, alterado_em, {', '.join(campos)})"
                f" VALUES (?, ?, ?{', ?' * len(campos)})",
                (item["uid"], item["nome"], item["alterado_em"], *valores),
            ).lastrowid
        else:
            c.execute(
                f"UPDATE {tabela} SET uid = ?, nome = ?, alterado_em = ?, {atribuicoes}"
                " WHERE id = ?",
                (item["uid"], item["nome"], item["alterado_em"], *valores, id_),
            )
        ids[item["uid"]] = id_
    return ids
