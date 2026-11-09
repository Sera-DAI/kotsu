import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ferramentas"))


@pytest.fixture
def banco():
    from money_cli.armazenamento.banco import Banco

    b = Banco.em_memoria()
    yield b
    b.fechar()
