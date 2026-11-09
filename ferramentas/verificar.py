"""Verificador do Money CLI, em dois níveis.

    python ferramentas/verificar.py --rapido   lint, camadas e testes rápidos
    python ferramentas/verificar.py            tudo, inclusive testes lentos

Rode antes de cada commit; o completo antes de cada PR.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _passo(nome: str, comando: list[str]) -> bool:
    inicio = time.perf_counter()
    resultado = subprocess.run(comando, cwd=RAIZ)
    duracao = time.perf_counter() - inicio
    estado = "ok" if resultado.returncode == 0 else "FALHOU"
    print(f"--> {nome}: {estado} ({duracao:.1f} s)\n", flush=True)
    return resultado.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rapido", action="store_true", help="pula os testes lentos")
    args = parser.parse_args(argv)

    py = sys.executable
    passos = [
        ("ruff (lint)", [py, "-m", "ruff", "check", "."]),
        ("ruff (formato)", [py, "-m", "ruff", "format", "--check", "."]),
        ("camadas", [py, "ferramentas/camadas.py"]),
        ("testes", [py, "-m", "pytest", *(["-m", "not lento"] if args.rapido else [])]),
    ]
    falhas = [nome for nome, comando in passos if not _passo(nome, comando)]
    nivel = "rápido" if args.rapido else "completo"
    if falhas:
        print(f"Verificador {nivel}: FALHOU em {', '.join(falhas)}")
        return 1
    print(f"Verificador {nivel}: tudo ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
