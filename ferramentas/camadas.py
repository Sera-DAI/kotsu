"""Confere a regra de dependência entre as camadas do Money CLI.

    dominio        -> nada (e nenhum módulo de I/O)
    armazenamento  -> dominio
    tela           -> dominio, armazenamento (mas não fala com o SQLite direto)

Uso: python ferramentas/camadas.py [pasta-do-pacote]
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

PACOTE = "money_cli"
RAIZ_PADRAO = Path(__file__).resolve().parent.parent / "src" / PACOTE

PERMITIDAS = {
    "dominio": set(),
    "armazenamento": {"dominio"},
    "tela": {"dominio", "armazenamento"},
}

# Módulos externos proibidos por camada (nome de topo).
PROIBIDOS = {
    "dominio": {
        "sqlite3",
        "os",
        "io",
        "pathlib",
        "shutil",
        "tempfile",
        "glob",
        "socket",
        "subprocess",
        "urllib",
        "http",
        "requests",
        "textual",
        "rich",
        "sys",
        "importlib",
    },
    "armazenamento": {"textual", "rich"},
    "tela": {"sqlite3"},
}


@dataclass(frozen=True)
class Violacao:
    arquivo: Path
    linha: int
    camada: str
    importa: str

    def __str__(self) -> str:
        local = f"{self.arquivo}:{self.linha}"
        return f"{local}: camada '{self.camada}' não pode importar '{self.importa}'"


def _modulo_do_arquivo(arquivo: Path, raiz: Path) -> list[str]:
    partes = list(arquivo.relative_to(raiz).with_suffix("").parts)
    if partes[-1] == "__init__":
        partes.pop()
    return [PACOTE, *partes]


def _importacoes(arvore: ast.AST, modulo: list[str], eh_pacote: bool):
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for nome in no.names:
                yield no.lineno, nome.name
        elif isinstance(no, ast.ImportFrom):
            if no.level:  # import relativo: resolve contra o pacote atual
                base = modulo if eh_pacote else modulo[:-1]
                base = base[: len(base) - (no.level - 1)]
                alvo = ".".join(base + ([no.module] if no.module else []))
            else:
                alvo = no.module or ""
            yield no.lineno, alvo
            if not no.module or no.level:
                for nome in no.names:  # from . import tela
                    yield no.lineno, f"{alvo}.{nome.name}"


def verificar(raiz: Path = RAIZ_PADRAO) -> list[Violacao]:
    violacoes = []
    for camada in PERMITIDAS:
        pasta = raiz / camada
        if not pasta.is_dir():
            raise FileNotFoundError(f"camada '{camada}' não encontrada em {raiz}")
        for arquivo in sorted(pasta.rglob("*.py")):
            modulo = _modulo_do_arquivo(arquivo, raiz)
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
            for linha, alvo in _importacoes(arvore, modulo, arquivo.name == "__init__.py"):
                partes = alvo.split(".")
                if partes[0] == PACOTE:
                    outra = partes[1] if len(partes) > 1 else None
                    if outra in PERMITIDAS and outra != camada and outra not in PERMITIDAS[camada]:
                        violacoes.append(Violacao(arquivo, linha, camada, alvo))
                elif partes[0] in PROIBIDOS[camada]:
                    violacoes.append(Violacao(arquivo, linha, camada, alvo))
    return violacoes


def main(argv: list[str]) -> int:
    raiz = Path(argv[0]) if argv else RAIZ_PADRAO
    violacoes = verificar(raiz)
    for v in violacoes:
        print(v)
    print("camadas: ok" if not violacoes else f"camadas: {len(violacoes)} violação(ões)")
    return 1 if violacoes else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
