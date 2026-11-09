import datetime as dt
import subprocess
import sys
import time

import pytest
from textual.widgets import DataTable, Static

from money_cli.dominio.tipos import NovoLancamento, Parcela, Tipo
from money_cli.tela.app import MoneyApp

HOJE = dt.date(2026, 11, 8)


async def test_abre_vazio_em_menos_de_1s(banco):
    inicio = time.perf_counter()
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.pause()
        decorrido = time.perf_counter() - inicio
        assert app.query_one("#vazio", Static).display
        assert not app.query_one("#lancamentos", DataTable).display
        topo = str(app.query_one("#topo", Static).render())
        assert "Novembro de 2026" in topo and "0,00" in topo
        await piloto.press("q")
    assert decorrido < 1.0, f"abriu em {decorrido:.2f} s"


async def test_troca_de_mes_e_mostra_lancamentos(banco):
    nubank = banco.criar_conta("Nubank", "#8a2be2")
    grupo = banco.novo_grupo_parcela()
    banco.inserir_lancamentos(
        [
            NovoLancamento(
                dt.date(2026, 10, 2),
                "geladeira",
                12000,
                Tipo.DESPESA,
                nubank.id,
                parcela=Parcela(grupo, 3, 10),
            ),
        ]
    )
    app = MoneyApp(banco, hoje=HOJE)
    async with app.run_test() as piloto:
        await piloto.press("left")
        tabela = app.query_one("#lancamentos", DataTable)
        assert app.mes.mes == 10 and tabela.display and tabela.row_count == 1
        assert "geladeira 3/10" in str(tabela.get_row_at(0)[1])
        assert "120,00" in str(app.query_one("#topo", Static).render())
        await piloto.press("right", "right")
        assert app.mes.mes == 12 and not tabela.display


@pytest.mark.lento
def test_processo_real_inicia_rapido(tmp_path):
    """Importa tudo e abre o banco num processo novo, como o usuário faz."""
    codigo = (
        "import time; t=time.perf_counter();"
        "from money_cli.tela.app import MoneyApp;"
        "from money_cli.armazenamento.banco import Banco;"
        f"b=Banco.abrir(__import__('pathlib').Path(r'{tmp_path}')/'money.sqlite');"
        "print(time.perf_counter()-t)"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    )
    assert float(saida.stdout) < 1.0
