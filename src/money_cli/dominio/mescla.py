"""Mesclagem de dados entre aparelhos (D39). Puro: recebe e devolve estados.

Um *estado* é o conteúdo inteiro de um banco, como dicionário (o mesmo formato do arquivo
de troca): `contas`, `categorias`, `recorrencias`, `lancamentos` e `lapides`. Os registros
se referem uns aos outros por `uid`, nunca pelo `id` local.

Regras (as mesmas no app Android; os casos em `vetores/` valem para os dois):

- Cada registro tem `alterado_em`, um carimbo `milissegundos-contador-réplica` comparável
  como texto. No mesmo `uid`, vale o carimbo maior, com o registro inteiro.
- Lançamento excluído deixa uma lápide. Ela vence o lançamento se for mais nova que ele.
- Contas e categorias com o mesmo nome (sem diferenciar maiúsculas) viram uma só: fica o
  menor `uid` e o conteúdo mais novo.
- Séries: vale o modelo mais novo; `gerada_ate` é sempre o maior dos dois.

Mesclar é comutativo e pode repetir: A+B dá o mesmo que B+A, e juntar duas vezes o mesmo
arquivo não muda nada.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from money_cli.dominio import dinheiro

FORMATO = 1
CARIMBO_ZERO = "0000000000000-0000-00000000"
SECOES = ("contas", "categorias", "recorrencias", "lancamentos", "lapides")

_CARIMBO = re.compile(r"\d{13}-\d{4}-[0-9a-f]{8}")
_TIPOS = ("receita", "despesa")


class ErroDeTroca(ValueError):
    """Arquivo de troca que não dá para usar. A mensagem é mostrada ao usuário como está."""


# --- carimbos e identidade ---------------------------------------------------


def carimbo(agora_ms: int, ultimo: str, replica: str) -> str:
    """Próximo carimbo: nunca menor nem igual a `ultimo`, mesmo com o relógio atrasado."""
    ms, contador = int(ultimo[:13]), int(ultimo[14:18])
    if agora_ms > ms:
        ms, contador = agora_ms, 0
    elif contador < 9999:
        contador += 1
    else:
        ms, contador = ms + 1, 0
    return f"{ms:013d}-{contador:04d}-{replica}"


def uid_do_mes(grupo: str, ano: int, mes: int) -> str:
    """`uid` do mês gerado por uma série: igual em qualquer aparelho."""
    return f"{grupo}-{ano:04d}-{mes:02d}"


def chave_do_nome(nome: str) -> str:
    """Como dois nomes de conta ou categoria são comparados (Itaú = ITAÚ)."""
    return nome.strip().casefold()


# --- forma canônica e código de conferência -----------------------------------


def _texto(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "1" if valor else "0"
    return str(valor).replace("\\", "\\\\").replace("\n", "\\n").replace("\x1f", "\\u")


def _linha(prefixo: str, campos: Iterable[object]) -> str:
    return "\x1f".join([prefixo, *(_texto(c) for c in campos)])


def _linha_conta(c: dict) -> str:
    return _linha("C", (c["uid"], c["nome"], c["cor"]))


def _linha_categoria(c: dict) -> str:
    return _linha("G", (c["uid"], c["nome"], c["recorrente"]))


def _linha_recorrencia(r: dict) -> str:
    campos = ("grupo", "dia", "descricao", "valor", "tipo", "conta", "categoria", "encerrada")
    return _linha("R", (r[c] for c in campos))


def _linha_lancamento(lanc: dict) -> str:
    p = lanc["parcela"] or {}
    return _linha(
        "L",
        (
            lanc["uid"],
            lanc["data"],
            lanc["descricao"],
            lanc["valor"],
            lanc["tipo"],
            lanc["conta"],
            lanc["categoria"],
            p.get("grupo"),
            p.get("numero"),
            p.get("total"),
            lanc["recorrencia"],
        ),
    )


def forma_canonica(estado: dict) -> str:
    """Texto que resume o conteúdo, igual em qualquer aparelho com os mesmos dados.

    Uma linha por registro, campos separados por U+001F, cada seção em ordem de `uid`.
    Ficam de fora os carimbos, `gerada_ate` e os meses gerados por série e nunca mexidos
    (`gerado`): cada aparelho gera meses futuros até onde a pessoa navegou.
    """
    linhas = sorted(_linha_conta(c) for c in estado["contas"])
    linhas += sorted(_linha_categoria(c) for c in estado["categorias"])
    linhas += sorted(_linha_recorrencia(r) for r in estado["recorrencias"])
    linhas += sorted(_linha_lancamento(x) for x in estado["lancamentos"] if not x["gerado"])
    linhas += sorted(_linha("X", (x["uid"],)) for x in estado["lapides"])
    return "\n".join(linhas)


def codigo(estado: dict) -> str:
    """Código de conferência: 12 dígitos hexadecimais do SHA-256 da forma canônica."""
    h = hashlib.sha256(forma_canonica(estado).encode("utf-8")).hexdigest()
    return f"{h[0:4]}-{h[4:8]}-{h[8:12]}"


# --- validação ---------------------------------------------------------------


def validar(estado: object) -> dict:
    """Confere um estado vindo de arquivo. Levanta `ErroDeTroca`; devolve o próprio estado."""
    if not isinstance(estado, dict) or estado.get("app") != "kotsu":
        raise ErroDeTroca("este arquivo não é uma exportação do Kotsu")
    formato = estado.get("formato")
    if not isinstance(formato, int) or isinstance(formato, bool) or formato < 1:
        raise ErroDeTroca("este arquivo não é uma exportação do Kotsu")
    if formato > FORMATO:
        raise ErroDeTroca(
            f"arquivo no formato {formato}, mais novo que este Kotsu (formato {FORMATO}):"
            " atualize o Kotsu neste aparelho"
        )
    try:
        _validar_conteudo(estado)
    except (KeyError, TypeError, AttributeError) as erro:
        raise ErroDeTroca(f"arquivo de troca incompleto ou estragado ({erro})") from None
    return estado


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise ErroDeTroca(f"arquivo de troca inválido: {mensagem}")


def _inteiro(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _texto_cheio(valor: object) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _data(valor: object) -> bool:
    try:
        return isinstance(valor, str) and dt.date.fromisoformat(valor).isoformat() == valor
    except ValueError:
        return False


def _carimbo_valido(valor: object) -> bool:
    return isinstance(valor, str) and _CARIMBO.fullmatch(valor) is not None


def _validar_conteudo(estado: dict) -> None:
    for secao in SECOES:
        _exigir(isinstance(estado[secao], list), f"falta a lista de {secao}")

    for secao, rotulo in (("contas", "conta"), ("categorias", "categoria")):
        uids, nomes = set(), set()
        for item in estado[secao]:
            _exigir(_texto_cheio(item["uid"]), f"{rotulo} sem uid")
            _exigir(_texto_cheio(item["nome"]), f"{rotulo} sem nome")
            _exigir(_carimbo_valido(item["alterado_em"]), f"carimbo da {rotulo} {item['nome']}")
            _exigir(item["uid"] not in uids, f"{rotulo} repetida ({item['nome']})")
            _exigir(chave_do_nome(item["nome"]) not in nomes, f"{rotulo} repetida ({item['nome']})")
            uids.add(item["uid"])
            nomes.add(chave_do_nome(item["nome"]))
    for conta in estado["contas"]:
        _exigir(isinstance(conta["cor"], str), f"cor da conta {conta['nome']}")
    for categoria in estado["categorias"]:
        _exigir(isinstance(categoria["recorrente"], bool), f"categoria {categoria['nome']}")
    contas = {c["uid"] for c in estado["contas"]}
    categorias = {c["uid"] for c in estado["categorias"]}

    def movimento(item: dict, oque: str) -> None:
        _exigir(isinstance(item["descricao"], str), f"descrição de {oque}")
        _exigir(_inteiro(item["valor"]) and item["valor"] > 0, f"valor de {oque}")
        _exigir(item["tipo"] in _TIPOS, f"tipo de {oque}")
        _exigir(item["conta"] in contas, f"conta desconhecida em {oque}")
        _exigir(
            item["categoria"] is None or item["categoria"] in categorias,
            f"categoria desconhecida em {oque}",
        )
        _exigir(_carimbo_valido(item["alterado_em"]), f"carimbo de {oque}")

    series = set()
    for serie in estado["recorrencias"]:
        _exigir(_texto_cheio(serie["grupo"]), "série sem grupo")
        oque = f"série {serie['grupo']}"
        _exigir(serie["grupo"] not in series, f"{oque} repetida")
        series.add(serie["grupo"])
        _exigir(_inteiro(serie["dia"]) and 1 <= serie["dia"] <= 31, f"dia da {oque}")
        _exigir(_data(serie["gerada_ate"]), f"gerada_ate da {oque}")
        _exigir(isinstance(serie["encerrada"], bool), f"encerrada da {oque}")
        movimento(serie, oque)

    uids = set()
    for lanc in estado["lancamentos"]:
        _exigir(_texto_cheio(lanc["uid"]), "lançamento sem uid")
        oque = f"lançamento {lanc['uid']}"
        _exigir(lanc["uid"] not in uids, f"{oque} repetido")
        uids.add(lanc["uid"])
        _exigir(_data(lanc["data"]), f"data do {oque}")
        _exigir(isinstance(lanc["gerado"], bool), f"gerado do {oque}")
        _exigir(
            lanc["recorrencia"] is None or lanc["recorrencia"] in series,
            f"série desconhecida no {oque}",
        )
        parcela = lanc["parcela"]
        if parcela is not None:
            _exigir(_texto_cheio(parcela["grupo"]), f"parcela do {oque}")
            _exigir(
                _inteiro(parcela["numero"])
                and _inteiro(parcela["total"])
                and 1 <= parcela["numero"] <= parcela["total"],
                f"parcela do {oque}",
            )
        movimento(lanc, oque)

    lapides = set()
    for lapide in estado["lapides"]:
        _exigir(_texto_cheio(lapide["uid"]), "exclusão sem uid")
        _exigir(lapide["uid"] not in lapides, f"exclusão repetida ({lapide['uid']})")
        lapides.add(lapide["uid"])
        _exigir(_carimbo_valido(lapide["excluido_em"]), f"carimbo da exclusão {lapide['uid']}")


# --- mesclagem ---------------------------------------------------------------


def _mais_novo(a: dict | None, b: dict, linha) -> dict:
    """O registro de carimbo maior; no empate (não deveria haver), a maior linha canônica."""
    if a is None:
        return b
    return max(a, b, key=lambda x: (x["alterado_em"], linha(x)))


def _unir_por_nome(a: list[dict], b: list[dict], linha) -> tuple[list[dict], dict[str, str]]:
    """Junta contas (ou categorias) dos dois lados. Devolve a lista e `uid antigo -> novo`."""
    por_uid: dict[str, dict] = {}
    for item in (*a, *b):
        por_uid[item["uid"]] = _mais_novo(por_uid.get(item["uid"]), item, linha)
    grupos: dict[str, list[dict]] = {}
    for uid in sorted(por_uid):
        grupos.setdefault(chave_do_nome(por_uid[uid]["nome"]), []).append(por_uid[uid])
    unidos, troca = [], {}
    for grupo in grupos.values():  # em ordem de uid: o primeiro é o menor
        conteudo = max(grupo, key=lambda x: x["alterado_em"])  # empate: o de menor uid
        unidos.append({**conteudo, "uid": grupo[0]["uid"]})
        for item in grupo:
            troca[item["uid"]] = grupo[0]["uid"]
    return sorted(unidos, key=lambda x: x["uid"]), troca


def mesclar(a: dict, b: dict) -> dict:
    """Junta dois estados válidos num só (só as seções de dados, cada uma em ordem de uid)."""
    contas, troca_conta = _unir_por_nome(a["contas"], b["contas"], _linha_conta)
    categorias, troca_categoria = _unir_por_nome(a["categorias"], b["categorias"], _linha_categoria)

    def apontar(item: dict) -> dict:
        categoria = item["categoria"]
        return {
            **item,
            "conta": troca_conta[item["conta"]],
            "categoria": None if categoria is None else troca_categoria[categoria],
        }

    series: dict[str, dict] = {}
    for serie in (*a["recorrencias"], *b["recorrencias"]):
        serie = apontar(serie)
        outra = series.get(serie["grupo"])
        vence = _mais_novo(outra, serie, _linha_recorrencia)
        gerada = (
            serie["gerada_ate"] if outra is None else max(outra["gerada_ate"], serie["gerada_ate"])
        )
        series[serie["grupo"]] = {**vence, "gerada_ate": gerada}

    lapides: dict[str, str] = {}
    for lapide in (*a["lapides"], *b["lapides"]):
        lapides[lapide["uid"]] = max(lapides.get(lapide["uid"], ""), lapide["excluido_em"])

    lancamentos: dict[str, dict] = {}
    for lanc in (*a["lancamentos"], *b["lancamentos"]):
        lanc = apontar(lanc)
        lancamentos[lanc["uid"]] = _mais_novo(
            lancamentos.get(lanc["uid"]),
            lanc,
            lambda x: _linha_lancamento(x) + _texto(x["gerado"]),
        )
    vivos = [x for x in lancamentos.values() if lapides.get(x["uid"], "") < x["alterado_em"]]

    return {
        "contas": contas,
        "categorias": categorias,
        "recorrencias": sorted(series.values(), key=lambda x: x["grupo"]),
        "lancamentos": sorted(vivos, key=lambda x: x["uid"]),
        "lapides": [{"uid": uid, "excluido_em": lapides[uid]} for uid in sorted(lapides)],
    }


def maior_carimbo(estado: dict) -> str:
    """O maior carimbo que aparece no estado (para o relógio local passar dele)."""
    carimbos = [CARIMBO_ZERO]
    for secao in ("contas", "categorias", "recorrencias", "lancamentos"):
        carimbos += [x["alterado_em"] for x in estado[secao]]
    carimbos += [x["excluido_em"] for x in estado["lapides"]]
    return max(carimbos)


# --- comparação (para conferir) -----------------------------------------------


@dataclass(frozen=True, slots=True)
class Resumo:
    """O que a mesclagem mudou neste aparelho, em lançamentos."""

    entraram: int = 0
    mudaram: int = 0
    sairam: int = 0

    @property
    def nada(self) -> bool:
        return not (self.entraram or self.mudaram or self.sairam)


def resumir(antes: dict, depois: dict) -> Resumo:
    """Compara os lançamentos de antes e depois de mesclar."""
    velhos = {x["uid"]: _visivel(x, antes) for x in antes["lancamentos"]}
    novos = {x["uid"]: _visivel(x, depois) for x in depois["lancamentos"]}
    return Resumo(
        entraram=len(novos.keys() - velhos.keys()),
        mudaram=sum(1 for uid in novos.keys() & velhos.keys() if novos[uid] != velhos[uid]),
        sairam=len(velhos.keys() - novos.keys()),
    )


def _nomes(estado: dict, secao: str) -> dict[str, str]:
    return {x["uid"]: x["nome"] for x in estado[secao]}


def _visivel(lanc: dict, estado: dict, nomes: tuple[dict, dict] | None = None) -> tuple:
    """O que a pessoa vê do lançamento, com nomes no lugar de uids."""
    contas, categorias = nomes or (_nomes(estado, "contas"), _nomes(estado, "categorias"))
    p = lanc["parcela"] or {}
    return (
        lanc["data"],
        lanc["descricao"],
        lanc["valor"],
        lanc["tipo"],
        chave_do_nome(contas[lanc["conta"]]),
        chave_do_nome(categorias[lanc["categoria"]]) if lanc["categoria"] else None,
        p.get("numero"),
        p.get("total"),
    )


@dataclass(frozen=True, slots=True)
class Comparacao:
    """Diferenças entre os dados daqui e os de um arquivo de outro aparelho."""

    codigo_aqui: str
    codigo_la: str
    so_aqui: list[dict] = field(default_factory=list)
    so_la: list[dict] = field(default_factory=list)
    diferentes: list[tuple[dict, dict]] = field(default_factory=list)  # (aqui, lá)

    @property
    def iguais(self) -> bool:
        return self.codigo_aqui == self.codigo_la


def comparar(aqui: dict, la: dict) -> Comparacao:
    """Lista os lançamentos que só existem de um lado ou que diferem.

    Mês gerado por série e nunca mexido não conta como diferença, a não ser que o outro
    lado o tenha excluído.
    """
    nomes_aqui = (_nomes(aqui, "contas"), _nomes(aqui, "categorias"))
    nomes_la = (_nomes(la, "contas"), _nomes(la, "categorias"))
    daqui = {x["uid"]: x for x in aqui["lancamentos"]}
    de_la = {x["uid"]: x for x in la["lancamentos"]}
    lapides_aqui = {x["uid"] for x in aqui["lapides"]}
    lapides_la = {x["uid"] for x in la["lapides"]}
    so_aqui, so_la, diferentes = [], [], []
    for uid in sorted(daqui.keys() | de_la.keys()):
        meu, dele = daqui.get(uid), de_la.get(uid)
        if meu and dele:
            if (not meu["gerado"] or not dele["gerado"]) and _visivel(
                meu, aqui, nomes_aqui
            ) != _visivel(dele, la, nomes_la):
                diferentes.append((meu, dele))
        elif meu and (not meu["gerado"] or uid in lapides_la):
            so_aqui.append(meu)
        elif dele and (not dele["gerado"] or uid in lapides_aqui):
            so_la.append(dele)
    return Comparacao(codigo(aqui), codigo(la), so_aqui, so_la, diferentes)


def descrever(lanc: dict, estado: dict) -> str:
    """Uma linha para mostrar o lançamento numa lista de diferenças."""
    contas, categorias = _nomes(estado, "contas"), _nomes(estado, "categorias")
    dia = dt.date.fromisoformat(lanc["data"]).strftime("%d/%m/%Y")
    sinal = "+" if lanc["tipo"] == "receita" else "-"
    partes = [dia, f"{sinal}{dinheiro.formatar(lanc['valor'])}"]
    if lanc["descricao"]:
        partes.append(lanc["descricao"])
    if lanc["parcela"]:
        partes.append(f"{lanc['parcela']['numero']}/{lanc['parcela']['total']}")
    if lanc["categoria"]:
        partes.append(f"#{categorias[lanc['categoria']]}")
    partes.append(f"@{contas[lanc['conta']]}")
    return " ".join(partes)
