"""Gera os casos de teste compartilhados entre o Kotsu do PC (Python) e o do Android (Kotlin).

    python ferramentas/gerar_vetores.py            regrava vetores/*.json
    python ferramentas/gerar_vetores.py --conferir  falha se os arquivos estão desatualizados

Cada arquivo de `vetores/` é uma lista de casos: entradas e a saída que as duas
implementações têm de dar (D39). As entradas ficam neste script; as saídas vêm do domínio
em Python, que é a referência. Mudou uma regra? Acrescente o caso aqui, regrave e confira o
diff do JSON antes de fazer o commit.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from money_cli.dominio import dinheiro, mescla, parcelas, recorrencia  # noqa: E402
from money_cli.dominio.linha import ErroDeLinha, interpretar  # noqa: E402
from money_cli.dominio.mes import Mes  # noqa: E402

PASTA = RAIZ / "vetores"

# --- linha rápida --------------------------------------------------------------

HOJE = "2026-11-11"
LINHAS = [
    "89,90 mercado #alimentação @nubank",
    "-89,90 mercado @nubank",
    "+3500 salário @itaú",
    "+3.500,00 salário @itaú 05/11",
    "120 geladeira #casa @nubank 10x",
    "120 geladeira #casa @nubank 10X 31/01/2027",
    "89.90 mercado @nubank",
    "1.234,56 viagem @nubank",
    "1.234 viagem @nubank",
    "1234,5 viagem @nubank",
    "12 café da manhã @nubank ontem",
    "12 café @nubank hoje",
    "12 café @nubank 1/2",
    "12 café @nubank 15/10/25",
    "12 café @nubank 29/02/2028",
    "12 @nubank",
    "12 café",
    "12    café   com   espaços   @nubank",
    "12 pix 2x1 @nubank",
    "12 nota 10/2026 @nubank",
    "12 a #b @c #d",
    "12 a @b @c",
    "12 a @b 2x 3x",
    "12 a @b 1x",
    "12 a @b 121x",
    "12 a @b 120x",
    "12 a @b 01/01 02/01",
    "12 a @b 31/02",
    "12 a #",
    "12 a @",
    "0 nada @b",
    "0,00 nada @b",
    "abc mercado @b",
    "12,345 mercado @b",
    "1.23.456 mercado @b",
    "1,2,3 mercado @b",
    "+ salário @b",
    "",
    "   ",
    "R$12 mercado @b",
    "12 MERCADO #Alimentação @NuBank",
]


def _linhas() -> list[dict]:
    casos = []
    for linha in LINHAS:
        caso: dict = {"linha": linha, "hoje": HOJE}
        try:
            lida = interpretar(linha, dt.date.fromisoformat(HOJE))
        except ErroDeLinha as erro:
            caso["erro"] = str(erro)
        else:
            caso["esperado"] = {
                "valor": lida.valor,
                "tipo": lida.tipo.value,
                "descricao": lida.descricao,
                "data": lida.data.isoformat(),
                "categoria": lida.categoria,
                "conta": lida.conta,
                "parcelas": lida.parcelas,
                "com_data": lida.com_data,
            }
        casos.append(caso)
    return casos


# --- datas e dinheiro ------------------------------------------------------------


def _datas() -> dict:
    primeiras = ["2026-01-31", "2026-11-11", "2027-12-15", "2028-01-29", "2026-08-30"]
    dias = [1, 15, 28, 29, 30, 31]
    meses = [(2026, 2), (2028, 2), (2026, 4), (2026, 12), (2100, 2)]
    return {
        "parcelas": [
            {
                "primeira": primeira,
                "indice": indice,
                "data": parcelas.data_da_parcela(
                    dt.date.fromisoformat(primeira), indice
                ).isoformat(),
            }
            for primeira in primeiras
            for indice in (0, 1, 2, 11, 12, 25)
        ],
        "recorrencia": [
            {
                "dia": dia,
                "ano": ano,
                "mes": mes,
                "data": recorrencia.data_no_mes(dia, Mes(ano, mes)).isoformat(),
            }
            for dia in dias
            for ano, mes in meses
        ],
        "uid_do_mes": [
            {"grupo": "serie1", "ano": 2026, "mes": 3, "uid": mescla.uid_do_mes("serie1", 2026, 3)},
            {"grupo": "s", "ano": 2027, "mes": 12, "uid": mescla.uid_do_mes("s", 2027, 12)},
        ],
    }


def _dinheiro() -> list[dict]:
    valores = [0, 1, 9, 10, 99, 100, 1250, 99999, 100000, 123456, 100000000, 123456789012, -8990]
    return [{"centavos": v, "texto": dinheiro.formatar(v)} for v in valores]


# --- carimbos --------------------------------------------------------------------


def _carimbos() -> list[dict]:
    entradas = [
        (1762850000000, mescla.CARIMBO_ZERO, "ab12cd34"),
        (1762850000000, "1762850000000-0000-ab12cd34", "ab12cd34"),
        (1762850000000, "1762850000000-0007-ffffffff", "ab12cd34"),
        (1762850000000, "1762850000000-9999-ab12cd34", "ab12cd34"),
        (1762849999999, "1762850000000-0003-ab12cd34", "ab12cd34"),  # relógio atrasou
        (1762850000001, "1762850000000-0003-ab12cd34", "00000000"),
        (5, mescla.CARIMBO_ZERO, "00000001"),
    ]
    return [
        {
            "agora_ms": ms,
            "ultimo": ultimo,
            "replica": replica,
            "carimbo": mescla.carimbo(ms, ultimo, replica),
        }
        for ms, ultimo, replica in entradas
    ]


# --- mesclagem -------------------------------------------------------------------


def _c(ms: int, replica: str = "aaaaaaaa", contador: int = 0) -> str:
    """Carimbo curto para os casos: `_c(5)` = 5 ms na réplica A."""
    return f"{ms:013d}-{contador:04d}-{replica}"


A, B = "aaaaaaaa", "bbbbbbbb"


def conta(uid: str, nome: str, em: str, cor: str = "#ff85bd") -> dict:
    return {"uid": uid, "nome": nome, "cor": cor, "alterado_em": em}


def categoria(uid: str, nome: str, em: str, recorrente: bool = False) -> dict:
    return {"uid": uid, "nome": nome, "recorrente": recorrente, "alterado_em": em}


def lanc(uid: str, em: str, **outros) -> dict:
    return {
        "uid": uid,
        "data": "2026-11-08",
        "descricao": "padaria",
        "valor": 1250,
        "tipo": "despesa",
        "conta": "c-nu",
        "categoria": None,
        "parcela": None,
        "recorrencia": None,
        "gerado": False,
        "alterado_em": em,
        **outros,
    }


def serie(grupo: str, em: str, **outros) -> dict:
    return {
        "grupo": grupo,
        "dia": 5,
        "descricao": "aluguel",
        "valor": 100000,
        "tipo": "despesa",
        "conta": "c-nu",
        "categoria": "g-alu",
        "gerada_ate": "2026-11-01",
        "encerrada": False,
        "alterado_em": em,
        **outros,
    }


def lapide(uid: str, em: str) -> dict:
    return {"uid": uid, "excluido_em": em}


def estado(**secoes) -> dict:
    base = {"app": "kotsu", "formato": mescla.FORMATO}
    return {**base, **{secao: secoes.get(secao, []) for secao in mescla.SECOES}}


NU = conta("c-nu", "nubank", _c(1))
ALU = categoria("g-alu", "aluguel", _c(1), recorrente=True)

CASOS_MESCLA: list[tuple[str, dict, dict]] = [
    ("dois estados vazios", estado(), estado()),
    (
        "lançamento criado em cada lado aparece nos dois",
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(10))]),
        estado(
            contas=[NU],
            lancamentos=[lanc("l-2", _c(11, B), descricao="uber", valor=2000)],
        ),
    ),
    (
        "mesmo lançamento editado nos dois lados: vale o carimbo maior, inteiro",
        estado(
            contas=[NU],
            lancamentos=[lanc("l-1", _c(20), descricao="padaria do zé", valor=1250)],
        ),
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(30, B), descricao="padaria", valor=1500)]),
    ),
    (
        "mesmo milissegundo: desempata o contador, depois a réplica",
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(20, A, 2), descricao="a")]),
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(20, B, 1), descricao="b")]),
    ),
    (
        "mesmo carimbo exato: desempata a réplica",
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(20, A), descricao="a")]),
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(20, B), descricao="b")]),
    ),
    (
        "excluído em um lado depois da última edição do outro: sai",
        estado(contas=[NU], lapides=[lapide("l-1", _c(40))]),
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(30, B))]),
    ),
    (
        "editado em um lado depois de excluído no outro: volta",
        estado(contas=[NU], lapides=[lapide("l-1", _c(40))]),
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(50, B), descricao="voltou")]),
    ),
    (
        "lápides dos dois lados: fica a mais nova",
        estado(lapides=[lapide("l-1", _c(40)), lapide("l-2", _c(41))]),
        estado(lapides=[lapide("l-1", _c(45, B))]),
    ),
    (
        "mesma conta criada nos dois lados: vira uma, com o menor uid e o conteúdo mais novo",
        estado(
            contas=[conta("c-zz", "Itaú", _c(5), cor="#ff7a00")],
            lancamentos=[lanc("l-1", _c(10), conta="c-zz")],
        ),
        estado(
            contas=[conta("c-aa", "ITAÚ", _c(7, B), cor="#0000ff")],
            lancamentos=[lanc("l-2", _c(11, B), conta="c-aa")],
        ),
    ),
    (
        "mesma categoria criada nos dois lados com outra grafia",
        estado(
            contas=[NU],
            categorias=[categoria("g-2", "Casa", _c(5))],
            lancamentos=[lanc("l-1", _c(10), categoria="g-2")],
        ),
        estado(
            contas=[NU],
            categorias=[categoria("g-1", "casa", _c(3, B)), categoria("g-9", "lazer", _c(4, B))],
            lancamentos=[lanc("l-2", _c(11, B), categoria="g-1")],
        ),
    ),
    (
        "categoria marcada como todo mês em um lado",
        estado(categorias=[categoria("g-1", "luz", _c(5), recorrente=False)]),
        estado(categorias=[categoria("g-1", "luz", _c(9, B), recorrente=True)]),
    ),
    (
        "compra parcelada feita em um lado entra inteira",
        estado(contas=[NU]),
        estado(
            contas=[NU],
            lancamentos=[
                lanc(
                    f"l-p{n}",
                    _c(10, B),
                    data=f"2026-{10 + n}-10",
                    descricao="geladeira",
                    valor=12000,
                    parcela={"grupo": "p-1", "numero": n, "total": 2},
                )
                for n in (1, 2)
            ],
        ),
    ),
    (
        "série: os dois lados geraram o mesmo mês; um gerou mais longe",
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2026-12-01")],
            lancamentos=[
                lanc(
                    "l-1",
                    _c(10),
                    data="2026-11-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                ),
                lanc(
                    "s-1-2026-12",
                    _c(10),
                    data="2026-12-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                    gerado=True,
                ),
            ],
        ),
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2027-01-01")],
            lancamentos=[
                lanc(
                    "l-1",
                    _c(10),
                    data="2026-11-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                ),
                lanc(
                    "s-1-2026-12",
                    _c(10),
                    data="2026-12-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                    gerado=True,
                ),
                lanc(
                    "s-1-2027-01",
                    _c(10),
                    data="2027-01-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                    gerado=True,
                ),
            ],
        ),
    ),
    (
        "série: mês gerado em um lado e excluído (só este) no outro continua excluído",
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2026-12-01")],
            lapides=[lapide("s-1-2026-12", _c(50))],
        ),
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2026-12-01")],
            lancamentos=[
                lanc(
                    "s-1-2026-12",
                    _c(10),
                    data="2026-12-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                    gerado=True,
                ),
            ],
        ),
    ),
    (
        "série: mês gerado em um lado e editado no outro fica com a edição",
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2026-12-01")],
            lancamentos=[
                lanc(
                    "s-1-2026-12",
                    _c(10),
                    data="2026-12-05",
                    descricao="aluguel",
                    valor=100000,
                    categoria="g-alu",
                    recorrencia="s-1",
                    gerado=True,
                ),
            ],
        ),
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2026-12-01")],
            lancamentos=[
                lanc(
                    "s-1-2026-12",
                    _c(60, B),
                    data="2026-12-05",
                    descricao="aluguel",
                    valor=110000,
                    categoria="g-alu",
                    recorrencia="s-1",
                    gerado=False,
                ),
            ],
        ),
    ),
    (
        "série: encerrada em um lado, modelo mais velho no outro",
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(70), gerada_ate="2026-12-01", encerrada=True)],
        ),
        estado(
            contas=[NU],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10), gerada_ate="2027-03-01")],
        ),
    ),
    (
        "série e lançamento seguem a conta unificada",
        estado(
            contas=[conta("c-nu", "nubank", _c(1))],
            categorias=[ALU],
            recorrencias=[serie("s-1", _c(10))],
        ),
        estado(
            contas=[conta("c-b", "Nubank", _c(2, B))],
            categorias=[categoria("g-b", "Aluguel", _c(2, B), recorrente=True)],
            recorrencias=[serie("s-2", _c(12, B), conta="c-b", categoria="g-b", dia=31)],
            lancamentos=[lanc("l-9", _c(12, B), conta="c-b", categoria="g-b", recorrencia="s-2")],
        ),
    ),
    (
        "descrição com separadores e acentos entra igual no código",
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(10), descricao="pão\\de\x1fló\nção")]),
        estado(contas=[NU], lancamentos=[lanc("l-1", _c(10), descricao="pão\\de\x1fló\nção")]),
    ),
]


def _mesclas() -> list[dict]:
    casos = []
    for nome, a, b in CASOS_MESCLA:
        mescla.validar(a)
        mescla.validar(b)
        esperado = mescla.mesclar(a, b)
        casos.append(
            {
                "nome": nome,
                "a": a,
                "b": b,
                "esperado": esperado,
                "codigo_a": mescla.codigo(a),
                "codigo_b": mescla.codigo(b),
                "codigo_esperado": mescla.codigo(esperado),
                "forma_canonica_esperada": mescla.forma_canonica(esperado),
            }
        )
    return casos


# --- arquivos inválidos ------------------------------------------------------------


def _invalidos() -> list[dict]:
    bom = estado(contas=[NU], categorias=[ALU], lancamentos=[lanc("l-1", _c(10))])
    entradas: list[tuple[str, object]] = [
        ("não é objeto", []),
        ("outro app", {**bom, "app": "outro"}),
        ("sem formato", {k: v for k, v in bom.items() if k != "formato"}),
        ("formato mais novo", {**bom, "formato": mescla.FORMATO + 1}),
        ("falta uma seção", {k: v for k, v in bom.items() if k != "lapides"}),
        ("valor zero", {**bom, "lancamentos": [lanc("l-1", _c(10), valor=0)]}),
        ("valor com casas", {**bom, "lancamentos": [lanc("l-1", _c(10), valor=12.5)]}),
        ("tipo desconhecido", {**bom, "lancamentos": [lanc("l-1", _c(10), tipo="outro")]}),
        ("data impossível", {**bom, "lancamentos": [lanc("l-1", _c(10), data="2026-02-30")]}),
        ("conta desconhecida", {**bom, "lancamentos": [lanc("l-1", _c(10), conta="c-x")]}),
        ("categoria desconhecida", {**bom, "lancamentos": [lanc("l-1", _c(10), categoria="g-x")]}),
        ("série desconhecida", {**bom, "lancamentos": [lanc("l-1", _c(10), recorrencia="s-x")]}),
        ("lançamento repetido", {**bom, "lancamentos": [lanc("l-1", _c(10)), lanc("l-1", _c(11))]}),
        ("carimbo torto", {**bom, "lancamentos": [lanc("l-1", "ontem")]}),
        (
            "parcela fora do total",
            {
                **bom,
                "lancamentos": [
                    lanc("l-1", _c(10), parcela={"grupo": "p", "numero": 3, "total": 2})
                ],
            },
        ),
        (
            "contas com o mesmo nome",
            {**bom, "contas": [NU, conta("c-2", "NUBANK", _c(2))]},
        ),
        ("lançamento sem campo", {**bom, "lancamentos": [{"uid": "l-1"}]}),
    ]
    casos = []
    for nome, entrada in entradas:
        try:
            mescla.validar(entrada)
        except mescla.ErroDeTroca as erro:
            casos.append({"nome": nome, "arquivo": entrada, "erro": str(erro)})
        else:
            raise AssertionError(f"caso inválido passou na validação: {nome}")
    return casos


# --- arquivos ----------------------------------------------------------------------


def gerar() -> dict[str, object]:
    """Conteúdo de cada arquivo de `vetores/`, por nome."""
    return {
        "linha.json": _linhas(),
        "datas.json": _datas(),
        "dinheiro.json": _dinheiro(),
        "carimbo.json": _carimbos(),
        "mescla.json": _mesclas(),
        "invalidos.json": _invalidos(),
    }


def _texto(conteudo: object) -> str:
    return json.dumps(conteudo, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def desatualizados() -> list[str]:
    """Nomes dos arquivos de `vetores/` que não batem com o que este script gera."""
    errados = []
    for nome, conteudo in gerar().items():
        try:
            no_disco = json.loads((PASTA / nome).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            errados.append(nome)
            continue
        if no_disco != json.loads(_texto(conteudo)):
            errados.append(nome)
    return errados


def main(argv: list[str]) -> int:
    if "--conferir" in argv:
        errados = desatualizados()
        for nome in errados:
            print(f"vetores/{nome} está desatualizado: rode python ferramentas/gerar_vetores.py")
        return 1 if errados else 0
    PASTA.mkdir(exist_ok=True)
    for nome, conteudo in gerar().items():
        (PASTA / nome).write_text(_texto(conteudo), encoding="utf-8", newline="\n")
        print(f"vetores/{nome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
