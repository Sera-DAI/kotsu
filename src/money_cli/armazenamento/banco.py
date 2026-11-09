"""Conexão SQLite, migrações e gravação atômica.

Toda escrita passa por `Banco.transacao()`: ou grava tudo, ou nada.
Antes de migrar um banco que já tem dados, uma cópia é feita ao lado.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from money_cli.armazenamento import migracoes
from money_cli.dominio.filtro import SEM_FILTRO, Filtro
from money_cli.dominio.mes import Mes
from money_cli.dominio.recorrencia import data_no_mes, meses_a_gerar
from money_cli.dominio.tipos import (
    Alcance,
    Categoria,
    Conta,
    Lancamento,
    NovoLancamento,
    Parcela,
    Tipo,
)
from money_cli.dominio.totais import TotaisMes


def _conectar(caminho: Path | str) -> sqlite3.Connection:
    conexao = sqlite3.connect(caminho, isolation_level=None)  # transações explícitas
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA synchronous = FULL")
    return conexao


def versao_do_esquema(conexao: sqlite3.Connection) -> int:
    return conexao.execute("PRAGMA user_version").fetchone()[0]


def copiar_banco(origem: sqlite3.Connection, destino: Path) -> None:
    """Cópia consistente do banco aberto (API de backup do SQLite)."""
    alvo = sqlite3.connect(destino)
    try:
        origem.backup(alvo)
    finally:
        alvo.close()


def migrar(
    conexao: sqlite3.Connection,
    caminho: Path | None,
    lista: Sequence[migracoes.Migracao] | None = None,
) -> int:
    """Aplica as migrações pendentes, cada uma numa transação. Devolve a versão final."""
    lista = migracoes.carregar() if lista is None else lista
    atual = versao_do_esquema(conexao)
    pendentes = [m for m in lista if m.versao > atual]
    if atual > len(lista):
        raise RuntimeError(
            f"banco na versão {atual}, mas este Money CLI só conhece até {len(lista)}"
        )
    if pendentes and atual > 0 and caminho is not None:
        copiar_banco(conexao, caminho.with_name(f"{caminho.stem}.antes-v{atual + 1}.sqlite"))
    for migracao in pendentes:
        conexao.execute("BEGIN IMMEDIATE")
        try:
            for comando in _comandos(migracao.sql):
                conexao.execute(comando)
            conexao.execute(f"PRAGMA user_version = {migracao.versao}")
            conexao.execute("COMMIT")
        except BaseException:
            conexao.execute("ROLLBACK")
            raise
    return versao_do_esquema(conexao)


def _comandos(sql: str) -> list[str]:
    """Divide um script em comandos completos (sem usar executescript, que faz COMMIT)."""
    comandos, atual = [], ""
    for linha in sql.splitlines(keepends=True):
        atual += linha
        if sqlite3.complete_statement(atual):
            if atual.strip():
                comandos.append(atual)
            atual = ""
    resto = [
        linha
        for linha in atual.splitlines()
        if linha.strip() and not linha.strip().startswith("--")
    ]
    if resto:
        raise ValueError("migração termina com comando incompleto")
    return comandos


class Banco:
    def __init__(self, conexao: sqlite3.Connection, caminho: Path | None) -> None:
        self._conexao = conexao
        self.caminho = caminho

    @classmethod
    def abrir(cls, caminho: Path) -> Banco:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        conexao = _conectar(caminho)
        try:
            migrar(conexao, caminho)
        except BaseException:
            conexao.close()
            raise
        return cls(conexao, caminho)

    @classmethod
    def em_memoria(cls) -> Banco:
        conexao = _conectar(":memory:")
        migrar(conexao, None)
        return cls(conexao, None)

    def fechar(self) -> None:
        self._conexao.close()

    def backup_manual(self, agora: dt.datetime | None = None) -> Path | None:
        from money_cli.armazenamento.backup import backup_manual

        if self.caminho is None:
            return None
        try:
            return backup_manual(self._conexao, self.caminho, agora or dt.datetime.now())
        except sqlite3.Error:
            raise OSError("não foi possível copiar o banco SQLite") from None

    @property
    def versao(self) -> int:
        return versao_do_esquema(self._conexao)

    @contextmanager
    def transacao(self) -> Iterator[sqlite3.Connection]:
        """Tudo dentro do bloco é gravado junto, ou nada é gravado."""
        self._conexao.execute("BEGIN IMMEDIATE")
        try:
            yield self._conexao
        except BaseException:
            self._conexao.execute("ROLLBACK")
            raise
        else:
            self._conexao.execute("COMMIT")

    # --- contas e categorias -------------------------------------------------

    def criar_conta(self, nome: str, cor: str) -> Conta:
        with self.transacao() as c:
            cursor = c.execute("INSERT INTO conta (nome, cor) VALUES (?, ?)", (nome.strip(), cor))
        return Conta(cursor.lastrowid, nome.strip(), cor)

    def listar_contas(self) -> list[Conta]:
        linhas = self._conexao.execute("SELECT id, nome, cor FROM conta ORDER BY nome")
        return [Conta(*linha) for linha in linhas]

    def criar_categoria(self, nome: str, recorrente: bool = False) -> Categoria:
        with self.transacao() as c:
            cursor = c.execute(
                "INSERT INTO categoria (nome, recorrente) VALUES (?, ?)",
                (nome.strip(), int(recorrente)),
            )
        return Categoria(cursor.lastrowid, nome.strip(), recorrente)

    def listar_categorias(self) -> list[Categoria]:
        linhas = self._conexao.execute("SELECT id, nome, recorrente FROM categoria ORDER BY nome")
        return [Categoria(id_, nome, bool(rec)) for id_, nome, rec in linhas]

    def definir_recorrente(self, categoria_id: int, recorrente: bool) -> None:
        """Marca ou desmarca a categoria (D36). Séries já em andamento não mudam."""
        with self.transacao() as c:
            c.execute(
                "UPDATE categoria SET recorrente = ? WHERE id = ?", (int(recorrente), categoria_id)
            )

    def conta_por_nome(self, nome: str) -> Conta | None:
        """Busca ignorando maiúsculas, inclusive acentuadas (Itaú = ITAÚ)."""
        alvo = nome.strip().casefold()
        return next((c for c in self.listar_contas() if c.nome.casefold() == alvo), None)

    def categoria_por_nome(self, nome: str) -> Categoria | None:
        alvo = nome.strip().casefold()
        return next((c for c in self.listar_categorias() if c.nome.casefold() == alvo), None)

    # --- lançamentos ---------------------------------------------------------

    @staticmethod
    def novo_grupo_parcela() -> str:
        return uuid.uuid4().hex

    def inserir_lancamentos(self, novos: Sequence[NovoLancamento]) -> list[int]:
        """Insere vários lançamentos (ex.: todas as parcelas) numa transação só."""
        ids = []
        with self.transacao() as c:
            for n in novos:
                if n.grupo_recorrencia:
                    c.execute(
                        "INSERT INTO recorrencia (grupo, dia, descricao, valor, tipo, conta_id,"
                        " categoria_id, gerada_ate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            n.grupo_recorrencia,
                            n.data.day,
                            n.descricao,
                            n.valor,
                            n.tipo.value,
                            n.conta_id,
                            n.categoria_id,
                            Mes.de(n.data).inicio.isoformat(),
                        ),
                    )
                ids.append(_inserir(c, n))
        return ids

    def tornar_recorrente(self, id_: int) -> bool:
        """Faz do lançamento o começo de uma série mensal (D36). False se já é parcela
        ou já é recorrente."""
        item = self.lancamento(id_)
        if item is None or item.parcela or item.grupo_recorrencia:
            return False
        grupo = self.novo_grupo_parcela()
        with self.transacao() as c:
            c.execute(
                "INSERT INTO recorrencia (grupo, dia, descricao, valor, tipo, conta_id,"
                " categoria_id, gerada_ate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    grupo,
                    item.data.day,
                    item.descricao,
                    item.valor,
                    item.tipo.value,
                    item.conta_id,
                    item.categoria_id,
                    Mes.de(item.data).inicio.isoformat(),
                ),
            )
            c.execute("UPDATE lancamento SET grupo_recorrencia = ? WHERE id = ?", (grupo, id_))
        return True

    def estender_recorrencias(self, ate: Mes) -> int:
        """Gera os meses que faltam das séries ativas, até `ate` (D36). Devolve quantos.

        Só avança: mês excluído com "só este" nunca volta, e série encerrada não gera.
        """
        series = self._conexao.execute(
            "SELECT grupo, dia, descricao, valor, tipo, conta_id, categoria_id, gerada_ate"
            " FROM recorrencia WHERE encerrada = 0 AND gerada_ate < ?",
            (ate.inicio.isoformat(),),
        ).fetchall()
        if not series:
            return 0
        criados = 0
        with self.transacao() as c:
            for grupo, dia, descricao, valor, tipo, conta_id, categoria_id, gerada in series:
                meses = meses_a_gerar(Mes.de(dt.date.fromisoformat(gerada)), ate)
                for mes in meses:
                    _inserir(
                        c,
                        NovoLancamento(
                            data_no_mes(dia, mes),
                            descricao,
                            valor,
                            Tipo(tipo),
                            conta_id,
                            categoria_id,
                            grupo_recorrencia=grupo,
                        ),
                    )
                    criados += 1
                c.execute(
                    "UPDATE recorrencia SET gerada_ate = ? WHERE grupo = ?",
                    (ate.inicio.isoformat(), grupo),
                )
        return criados

    def lancamentos_do_mes(
        self, mes: Mes, limite: int = 200, desde: int = 0, filtro: Filtro = SEM_FILTRO
    ) -> list[Lancamento]:
        """Uma página do mês, mais recentes primeiro. `desde` é quantos pular."""
        onde, parametros = _onde_mes(mes, filtro)
        linhas = self._conexao.execute(
            "SELECT id, data, descricao, valor, tipo, conta_id, categoria_id,"
            " grupo_parcela, parcela_numero, parcela_total, grupo_recorrencia"
            f" FROM lancamento WHERE {onde}"
            " ORDER BY data DESC, id DESC LIMIT ? OFFSET ?",
            (*parametros, limite, desde),
        )
        return [_lancamento(linha) for linha in linhas]

    def lancamento(self, id_: int) -> Lancamento | None:
        linha = self._conexao.execute(
            "SELECT id, data, descricao, valor, tipo, conta_id, categoria_id,"
            " grupo_parcela, parcela_numero, parcela_total, grupo_recorrencia"
            " FROM lancamento WHERE id = ?",
            (id_,),
        ).fetchone()
        return _lancamento(linha) if linha else None

    def excluir(self, id_: int, alcance: Alcance = Alcance.TODAS) -> int:
        """Exclui o lançamento; se é parcela e alcance é TODAS, a compra inteira (D12).

        Devolve quantos lançamentos saíram.
        """
        onde, parametros = self._alvo(id_, alcance)
        with self.transacao() as c:
            if alcance is Alcance.PROXIMAS:  # encerra a série; meses passados ficam (D36)
                c.execute("UPDATE recorrencia SET encerrada = 1 WHERE grupo = ?", (parametros[0],))
            return c.execute(f"DELETE FROM lancamento WHERE {onde}", parametros).rowcount

    def renomear(self, id_: int, descricao: str, alcance: Alcance = Alcance.TODAS) -> int:
        """Troca a descrição; com parcela e alcance TODAS, de todas as parcelas (D12)."""
        onde, parametros = self._alvo(id_, alcance)
        with self.transacao() as c:
            if alcance is Alcance.PROXIMAS:
                c.execute(
                    "UPDATE recorrencia SET descricao = ? WHERE grupo = ?",
                    (descricao.strip(), parametros[0]),
                )
            return c.execute(
                f"UPDATE lancamento SET descricao = ? WHERE {onde}",
                (descricao.strip(), *parametros),
            ).rowcount

    def editar(self, id_: int, novo: NovoLancamento, alcance: Alcance = Alcance.TODAS) -> int:
        """Troca valor, tipo, descrição, conta e categoria (D28).

        A data muda só quando o alvo é um lançamento só; em TODAS as parcelas e em PROXIMAS
        as datas ficam como estão (PROXIMAS também muda o modelo da série, D36). Número e
        grupo de parcelas nunca mudam. Devolve quantos mudaram.
        """
        onde, parametros = self._alvo(id_, alcance)
        campos = "descricao = ?, valor = ?, tipo = ?, conta_id = ?, categoria_id = ?"
        valores: list = [novo.descricao.strip(), novo.valor, novo.tipo.value, novo.conta_id]
        valores.append(novo.categoria_id)
        if onde.startswith("id"):
            campos += ", data = ?"
            valores.append(novo.data.isoformat())
        with self.transacao() as c:
            if alcance is Alcance.PROXIMAS:
                c.execute(
                    "UPDATE recorrencia SET descricao = ?, valor = ?, tipo = ?, conta_id = ?,"
                    " categoria_id = ? WHERE grupo = ?",
                    (*valores[:5], parametros[0]),
                )
            return c.execute(
                f"UPDATE lancamento SET {campos} WHERE {onde}", (*valores, *parametros)
            ).rowcount

    def _alvo(self, id_: int, alcance: Alcance) -> tuple[str, tuple]:
        item = self.lancamento(id_)
        if item is not None and item.parcela and alcance is Alcance.TODAS:
            return "grupo_parcela = ?", (item.parcela.grupo,)
        if item is not None and item.grupo_recorrencia and alcance is Alcance.PROXIMAS:
            return "grupo_recorrencia = ? AND data >= ?", (
                item.grupo_recorrencia,
                item.data.isoformat(),
            )
        return "id = ?", (id_,)

    def totais_do_mes(self, mes: Mes, filtro: Filtro = SEM_FILTRO) -> TotaisMes:
        onde, parametros = _onde_mes(mes, filtro)
        linha = self._conexao.execute(
            f"SELECT {_SOMAS} FROM lancamento WHERE {onde}", parametros
        ).fetchone()
        return TotaisMes(*linha)

    def totais_por_conta(self, mes: Mes, filtro: Filtro = SEM_FILTRO) -> dict[int, TotaisMes]:
        """Receitas e despesas de cada conta que teve lançamento no mês (D9, D29)."""
        onde, parametros = _onde_mes(mes, filtro)
        linhas = self._conexao.execute(
            f"SELECT conta_id, {_SOMAS} FROM lancamento WHERE {onde} GROUP BY conta_id",
            parametros,
        )
        return {conta_id: TotaisMes(*resto) for conta_id, *resto in linhas}


_SOMAS = (
    "coalesce(sum(CASE WHEN tipo = 'receita' THEN valor END), 0),"
    " coalesce(sum(CASE WHEN tipo = 'despesa' THEN valor END), 0),"
    " count(*)"
)


def _onde_mes(mes: Mes, filtro: Filtro) -> tuple[str, tuple]:
    """Faixa de datas do mês (usa o índice) mais o filtro, se houver."""
    onde = "data >= ? AND data < ?"
    parametros: list = [mes.inicio.isoformat(), mes.fim_exclusivo.isoformat()]
    if filtro.conta_id is not None:
        onde += " AND conta_id = ?"
        parametros.append(filtro.conta_id)
    if filtro.categoria_id is not None:
        onde += " AND categoria_id = ?"
        parametros.append(filtro.categoria_id)
    return onde, tuple(parametros)


def _inserir(c: sqlite3.Connection, n: NovoLancamento) -> int:
    p = n.parcela
    return c.execute(
        "INSERT INTO lancamento (data, descricao, valor, tipo, conta_id, categoria_id,"
        " grupo_parcela, parcela_numero, parcela_total, grupo_recorrencia)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            n.data.isoformat(),
            n.descricao,
            n.valor,
            n.tipo.value,
            n.conta_id,
            n.categoria_id,
            p.grupo if p else None,
            p.numero if p else None,
            p.total if p else None,
            n.grupo_recorrencia,
        ),
    ).lastrowid


def _lancamento(linha: tuple) -> Lancamento:
    (id_, data, descricao, valor, tipo, conta_id, categoria_id, grupo, numero, total, rec) = linha
    parcela = Parcela(grupo, numero, total) if grupo is not None else None
    return Lancamento(
        id_,
        dt.date.fromisoformat(data),
        descricao,
        valor,
        Tipo(tipo),
        conta_id,
        categoria_id,
        parcela,
        rec,
    )
