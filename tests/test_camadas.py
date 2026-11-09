"""A regra de camadas, e a prova de que o teste pega uma violação de propósito."""

import shutil

import pytest

import camadas


def test_codigo_atual_respeita_as_camadas():
    assert camadas.verificar() == []


@pytest.fixture
def copia(tmp_path):
    destino = tmp_path / "money_cli"
    shutil.copytree(camadas.RAIZ_PADRAO, destino, ignore=shutil.ignore_patterns("__pycache__"))
    return destino


@pytest.mark.parametrize(
    ("arquivo", "linha", "proibido"),
    [
        ("dominio/mes.py", "from money_cli.tela.app import MoneyApp", "money_cli.tela.app"),
        ("dominio/mes.py", "import money_cli.armazenamento.banco", "money_cli.armazenamento"),
        ("dominio/tipos.py", "import sqlite3", "sqlite3"),
        ("dominio/tipos.py", "from pathlib import Path", "pathlib"),
        ("dominio/totais.py", "from ..tela import cores", "money_cli.tela"),
        ("armazenamento/banco.py", "from money_cli.tela import app", "money_cli.tela"),
        ("armazenamento/caminhos.py", "from textual.app import App", "textual.app"),
        ("tela/app.py", "import sqlite3", "sqlite3"),
    ],
)
def test_violacao_injetada_e_detectada(copia, arquivo, linha, proibido):
    alvo = copia / arquivo
    alvo.write_text(alvo.read_text(encoding="utf-8") + f"\n{linha}\n", encoding="utf-8")
    violacoes = camadas.verificar(copia)
    assert len(violacoes) >= 1
    assert all(v.arquivo == alvo for v in violacoes)
    assert any(v.importa.startswith(proibido) for v in violacoes)


def test_linha_de_comando_falha_com_violacao(copia, capsys):
    (copia / "dominio" / "novo.py").write_text("import money_cli.tela\n", encoding="utf-8")
    assert camadas.main([str(copia)]) == 1
    assert "violação" in capsys.readouterr().out
