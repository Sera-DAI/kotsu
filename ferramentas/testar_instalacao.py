"""Instala via pipx e verifica o pacote fora do checkout, com dados temporários.

Requer `python -m pip install pipx`. Usa rede apenas para instalar dependências;
não faz parte dos testes unitários nem acessa dados reais.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def executar(comando: list[str], pasta: Path, ambiente: dict[str, str]) -> str:
    resultado = subprocess.run(
        comando,
        cwd=pasta,
        env=ambiente,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if resultado.returncode:
        raise RuntimeError(resultado.stdout + resultado.stderr)
    return resultado.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="money-pipx-") as nome:
        pasta = Path(nome)
        ambiente = dict(os.environ)
        ambiente.pop("PYTHONPATH", None)
        ambiente.pop("MONEY_CLI_DADOS", None)
        ambiente.update(
            PIPX_HOME=str(pasta / "pipx"),
            PIPX_BIN_DIR=str(pasta / "bin"),
            PIPX_MAN_DIR=str(pasta / "man"),
            PIPX_DEFAULT_PYTHON=sys.executable,
            PIPX_LOG_DIR=str(pasta / "logs"),
            PIPX_CACHE_DIR=str(pasta / "cache"),
            UV_CACHE_DIR=str(pasta / "uv-cache"),
            PIP_CACHE_DIR=str(pasta / "pip-cache"),
            PYTHONUTF8="1",
        )
        executar([sys.executable, "-m", "pipx", "install", str(RAIZ)], pasta, ambiente)
        kotsu = pasta / "bin" / ("kotsu.exe" if sys.platform == "win32" else "kotsu")
        # O apelido antigo continua instalado.
        assert (pasta / "bin" / ("money.exe" if sys.platform == "win32" else "money")).exists()
        py = (
            pasta
            / "pipx"
            / "venvs"
            / "kotsu-cli"
            / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        )
        assert "money-cli" in executar([str(kotsu), "--version"], pasta, ambiente)
        assert "--dados" in executar([str(kotsu), "--help"], pasta, ambiente)
        dados = pasta / "dados"
        # Python do próprio venv do pipx, sem PYTHONPATH ou cwd do checkout.
        codigo = """
import asyncio
import datetime as dt
import sys
from pathlib import Path
import money_cli
from money_cli.armazenamento import migracoes
from money_cli.armazenamento.banco import Banco
from money_cli.tela.app import MoneyApp
from money_cli.dominio.tipos import NovoLancamento, Tipo
from textual.widgets import DataTable
assert Path(sys.argv[2]).resolve() not in Path(money_cli.__file__).resolve().parents
async def verificar():
    banco = Banco.abrir(Path(sys.argv[1]) / 'money.sqlite')
    try:
        assert banco.versao == len(migracoes.carregar()) >= 2
        conta = banco.criar_conta('Conta fictícia', '#8a2be2')
        banco.inserir_lancamentos([
            NovoLancamento(dt.date(2026, 11, 8), 'Café', 8990, Tipo.DESPESA, conta.id)
        ])
        app = MoneyApp(banco, hoje=dt.date(2026, 11, 8))
        async with app.run_test() as piloto:
            await piloto.pause()
            assert app.query_one('#lancamentos', DataTable).row_count == 1
            await piloto.press('b')
            await piloto.pause()
            await piloto.press('q')
        assert list((Path(sys.argv[1]) / 'backups').glob('money.*.sqlite'))
    finally:
        banco.fechar()
asyncio.run(verificar())
"""
        executar([str(py), "-c", codigo, str(dados), str(RAIZ)], pasta, ambiente)
        print("pipx: instalação, CLI, migrações, tela e backup ok fora do checkout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
