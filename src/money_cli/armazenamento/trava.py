"""Trava de uso (D38): evita abrir o mesmo banco em dois computadores ao mesmo tempo.

Com a pasta de dados num serviço de sincronização (Google Drive), dois computadores abertos
juntos geram "cópias em conflito" e perdem lançamentos. Enquanto o Kotsu está aberto existe
`kotsu.trava` ao lado do banco, dizendo quem está usando. A trava é um aviso entre
computadores, não uma garantia: o Drive leva alguns segundos para propagá-la.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

NOME_TRAVA = "kotsu.trava"


class BancoEmUso(Exception):
    """Outro Kotsu (ou outro computador) está com o banco aberto."""

    def __init__(self, maquina: str, desde: str, mesma_maquina: bool) -> None:
        self.maquina, self.desde, self.mesma_maquina = maquina, desde, mesma_maquina
        onde = "neste computador" if mesma_maquina else f"no computador {maquina}"
        super().__init__(f"O Kotsu já está aberto {onde} (desde {desde}).")


@dataclass
class Trava:
    caminho: Path

    def liberar(self) -> None:
        """Remove a trava, só se ainda for deste processo."""
        if (
            _ler(self.caminho).get("pid") == os.getpid()
            and _ler(self.caminho).get("maquina") == _maquina()
        ):
            self.caminho.unlink(missing_ok=True)


def tomar(pasta: Path, desde: str, forcar: bool = False) -> Trava:
    """Cria a trava ou levanta `BancoEmUso`. `forcar` assume uma trava de outro dono."""
    caminho = pasta / NOME_TRAVA
    pasta.mkdir(parents=True, exist_ok=True)
    dono = _ler(caminho)
    if dono and not forcar:
        mesma = dono.get("maquina") == _maquina()
        # Na mesma máquina, trava de processo que já morreu (queda de energia) é descartada.
        if not (mesma and not _vivo(int(dono.get("pid", 0)))):
            raise BancoEmUso(str(dono.get("maquina", "?")), str(dono.get("desde", "?")), mesma)
    conteudo = json.dumps({"maquina": _maquina(), "pid": os.getpid(), "desde": desde})
    caminho.unlink(missing_ok=True)
    try:
        descritor = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:  # dois Kotsu na mesma hora: perde quem chegou depois
        dono = _ler(caminho)
        raise BancoEmUso(
            str(dono.get("maquina", "?")),
            str(dono.get("desde", "?")),
            dono.get("maquina") == _maquina(),
        ) from None
    with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)
    return Trava(caminho)


def conflitos(pasta: Path, nome_banco: str) -> list[Path]:
    """Cópias do banco que o Drive cria ao ver duas edições (ex.: `money (1).sqlite`).

    Ignora o banco, backups e as cópias de pré-migração (`money.antes-v2.sqlite`).
    """
    stem = Path(nome_banco).stem
    padrao = re.compile(re.escape(stem) + r".+\.sqlite", re.IGNORECASE)
    antes = re.compile(re.escape(stem) + r"\.antes-v\d+\.sqlite", re.IGNORECASE)
    try:
        itens = sorted(pasta.iterdir())
    except OSError:
        return []
    return [
        p for p in itens if p.is_file() and padrao.fullmatch(p.name) and not antes.fullmatch(p.name)
    ]


def _maquina() -> str:
    return socket.gethostname()


def _ler(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Trava existe mas está ilegível (ainda sincronizando): trata como de dono desconhecido.
        return {"maquina": "?", "pid": 0, "desde": "?"} if caminho.exists() else {}
    return dados if isinstance(dados, dict) else {}


def _vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":  # os.kill(pid, 0) MATA o processo no Windows
        import ctypes

        kernel = ctypes.windll.kernel32
        processo = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not processo:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(processo, ctypes.byref(codigo))) and (
                codigo.value == 259  # STILL_ACTIVE
            )
        finally:
            kernel.CloseHandle(processo)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
