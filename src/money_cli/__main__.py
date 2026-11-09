"""Ponto de entrada: `money` ou `python -m money_cli`."""

from __future__ import annotations

import argparse
from pathlib import Path

from money_cli import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kotsu", description="Finanças pessoais no terminal.")
    parser.add_argument("--dados", type=Path, help="pasta de dados (padrão: pasta do usuário)")
    parser.add_argument("--version", action="version", version=f"money-cli {__version__}")
    args = parser.parse_args(argv)

    from money_cli.armazenamento.banco import Banco
    from money_cli.armazenamento.caminhos import arquivo_do_banco
    from money_cli.tela.app import MoneyApp

    arquivo = arquivo_do_banco(args.dados)
    banco = Banco.abrir(arquivo)
    try:
        MoneyApp(banco, pasta_tema=arquivo.parent).run()
    finally:
        banco.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
