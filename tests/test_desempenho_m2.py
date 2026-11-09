"""Critério 12 do M2: com 50 mil lançamentos, trocar de mês leva menos de 150 ms."""

import datetime as dt
import random
import statistics
import time

import pytest

from money_cli.armazenamento.banco import Banco
from money_cli.dominio.filtro import Filtro
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import NovoLancamento, Parcela, Tipo
from money_cli.tela.app import MoneyApp

LIMITE_MS = 150
HOJE = dt.date(2026, 11, 8)


def _banco_ficticio(caminho, quantidade=50_000, meses=60) -> Banco:
    """~830 lançamentos por mês em 5 anos, 6 contas, 12 categorias, 1 em 10 parcelado."""
    sorteio = random.Random(42)
    banco = Banco.abrir(caminho)
    contas = [banco.criar_conta(f"conta{i}", "#8a2be2").id for i in range(6)]
    categorias = [banco.criar_categoria(f"cat{i}").id for i in range(12)]
    inicio = Mes.de(HOJE).somar(-meses + 1)
    novos = []
    for i in range(quantidade):
        mes = inicio.somar(sorteio.randrange(meses))
        parcela = None
        if i % 10 == 0:
            parcela = Parcela(f"g{i}", sorteio.randint(1, 10), 10)
        novos.append(
            NovoLancamento(
                dt.date(mes.ano, mes.mes, sorteio.randint(1, 28)),
                f"loja {i}",
                sorteio.randint(100, 500_000),
                Tipo.RECEITA if i % 15 == 0 else Tipo.DESPESA,
                sorteio.choice(contas),
                sorteio.choice([None, *categorias]),
                parcela,
            )
        )
    banco.inserir_lancamentos(novos)
    return banco


@pytest.mark.lento
async def test_trocar_de_mes_com_50_mil_lancamentos(tmp_path):
    """Mede duas coisas a cada troca de mês, sem e com filtro:

    - consultas + montar a lista (`action_mes`): o pior caso tem de ficar abaixo do limite;
    - isso mais o redesenho da tela (`pause`): a mediana fica abaixo do limite. Só a
      mediana, porque a pausa do piloto de testes sozinha às vezes passa de 100 ms.
    """
    banco = _banco_ficticio(tmp_path / "money.sqlite")
    try:
        app = MoneyApp(banco, hoje=HOJE)
        resultados = {}
        async with app.run_test() as piloto:
            for nome, filtro in [("sem filtro", Filtro()), ("com filtro", Filtro(conta_id=1))]:
                app.filtro = filtro
                acao, total = [], []
                for passo in [-1] * 6 + [1] * 6:
                    inicio = time.perf_counter()
                    app.action_mes(passo)
                    acao.append((time.perf_counter() - inicio) * 1000)
                    await piloto.pause()
                    total.append((time.perf_counter() - inicio) * 1000)
                    assert app.query_one("#lancamentos").row_count > 0
                resultados[nome] = (max(acao), statistics.median(total))
        for nome, (pior, mediana) in resultados.items():
            print(f"{nome}: consultas e lista pior {pior:.0f} ms; com redesenho {mediana:.0f} ms")
            assert pior < LIMITE_MS, f"{nome}: trocar de mês levou {pior:.0f} ms"
            assert mediana < LIMITE_MS, f"{nome}: com redesenho levou {mediana:.0f} ms"
    finally:
        banco.fechar()
