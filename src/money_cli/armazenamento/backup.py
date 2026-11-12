"""Backup manual do SQLite: cada pedido publica uma cópia completa nova e mantém as 5 últimas."""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import tempfile
from pathlib import Path

MANTER = 5


def backup_manual(
    conexao: sqlite3.Connection,
    caminho: Path,
    agora: dt.datetime,
    pasta: Path | None = None,
) -> Path:
    from money_cli.armazenamento.banco import copiar_banco

    pasta = pasta or caminho.parent / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"{caminho.stem}.{agora:%Y-%m-%d-%H%M%S}"
    descritor, nome = tempfile.mkstemp(prefix=".backup-", suffix=".tmp", dir=pasta)
    os.close(descritor)  # Windows: fechar antes de SQLite abrir o mesmo arquivo.
    temporario = Path(nome)
    try:
        copiar_banco(conexao, temporario)
        with temporario.open("r+b") as arquivo:
            os.fsync(arquivo.fileno())
        # Mesmo segundo: sufixo maior que o de qualquer cópia existente, para que a ordem
        # por nome continue sendo a ordem de criação depois da poda.
        usados = [_numero(p.name, base) for p in pasta.glob(f"{base}*.sqlite")]
        for tentativa in range(max([0, *usados]) + 1, max([0, *usados]) + 1000):
            destino = pasta / (f"{base}.sqlite" if tentativa == 1 else f"{base}-{tentativa}.sqlite")
            try:
                # Publicação atômica sem sobrescrever cópia existente (NTFS e Linux).
                os.link(temporario, destino)
                break
            except FileExistsError:
                continue
        else:
            raise OSError("não foi possível escolher um nome livre para o backup")
    finally:
        temporario.unlink(missing_ok=True)
    _podar(pasta, caminho.stem)
    return destino


def _numero(nome: str, base: str) -> int:
    resto = nome[len(base) : -len(".sqlite")]
    return int(resto[1:]) if re.fullmatch(r"-\d+", resto) else 1 if resto == "" else 0


def _podar(pasta: Path, stem: str) -> None:
    """Só depois de publicar: mantém as `MANTER` mais recentes.

    Só olha cópias com o nome deste módulo (`money.AAAA-MM-DD-HHMMSS[-N].sqlite`); cópias de
    pré-migração, backups de outro formato e outros arquivos nunca são tocados.
    """
    padrao = re.compile(re.escape(stem) + r"\.(\d{4}-\d{2}-\d{2}-\d{6})(?:-(\d+))?\.sqlite")
    copias = []
    for arquivo in pasta.iterdir():
        achado = padrao.fullmatch(arquivo.name)
        if achado and arquivo.is_file():
            copias.append(((achado[1], int(achado[2] or 1)), arquivo))
    for _, antigo in sorted(copias, reverse=True)[MANTER:]:
        antigo.unlink(missing_ok=True)
