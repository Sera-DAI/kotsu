"""Pasta de dados sincronizada (D38): configuração, trava entre computadores, conflitos."""

import os

import pytest

from money_cli.__main__ import main
from money_cli.armazenamento import caminhos, trava
from money_cli.armazenamento.banco import Banco


@pytest.fixture
def local(tmp_path, monkeypatch):
    pasta = tmp_path / "local"
    monkeypatch.delenv("MONEY_CLI_DADOS", raising=False)
    monkeypatch.setenv("APPDATA", str(pasta))
    monkeypatch.setenv("XDG_DATA_HOME", str(pasta))
    return pasta / "money-cli"


def test_pasta_configurada_vale_e_variavel_de_ambiente_vence(local, tmp_path, monkeypatch):
    assert caminhos.pasta_de_dados() == local
    drive = tmp_path / "drive" / 'Kotsu "x"\\y'
    caminhos.gravar_pasta_configurada(drive)
    assert caminhos.pasta_de_dados() == drive
    assert caminhos.pasta_de_backups(drive) == local / "backups"
    monkeypatch.setenv("MONEY_CLI_DADOS", str(tmp_path / "outra"))
    assert caminhos.pasta_de_dados() == tmp_path / "outra"
    assert caminhos.pasta_de_backups(tmp_path / "outra") is None
    monkeypatch.delenv("MONEY_CLI_DADOS")
    caminhos.gravar_pasta_configurada(None)
    assert caminhos.pasta_de_dados() == local


def test_config_ilegivel_volta_ao_padrao(local):
    local.mkdir(parents=True)
    (local / caminhos.NOME_CONFIG).write_text("isto não é toml [[[", encoding="utf-8")
    assert caminhos.pasta_de_dados() == local


def test_configurar_copia_o_banco_e_backup_vai_para_pasta_local(local, tmp_path):
    banco = Banco.abrir(caminhos.arquivo_do_banco())
    banco.criar_conta("Nubank", "#ff00ff")
    banco.fechar()
    drive = tmp_path / "drive"
    from money_cli.__main__ import main

    assert main(["--pasta-dados", str(drive)]) == 0
    assert caminhos.pasta_de_dados() == drive.resolve()
    novo = Banco.abrir(caminhos.arquivo_do_banco(), caminhos.pasta_de_backups(drive.resolve()))
    assert [c.nome for c in novo.listar_contas()] == ["Nubank"]
    copia = novo.backup_manual()
    novo.fechar()
    assert copia.parent == local / "backups"
    assert not (drive / "backups").exists()


def test_configurar_recusa_quando_os_dois_lados_tem_banco(local, tmp_path, capsys):
    Banco.abrir(caminhos.arquivo_do_banco()).fechar()
    drive = tmp_path / "drive"
    Banco.abrir(caminhos.arquivo_do_banco(drive)).fechar()
    assert main(["--pasta-dados", str(drive)]) == 1
    assert "não junta" in capsys.readouterr().err
    assert caminhos.pasta_configurada() is None


def test_trava_bloqueia_outro_computador_e_forcar_assume(tmp_path, monkeypatch):
    minha = trava.tomar(tmp_path, "10/11/2026 09:00")
    monkeypatch.setattr(trava, "_maquina", lambda: "NOTEBOOK")
    with pytest.raises(trava.BancoEmUso) as erro:
        trava.tomar(tmp_path, "10/11/2026 09:05")
    assert not erro.value.mesma_maquina
    assert "10/11/2026 09:00" in str(erro.value)
    assumida = trava.tomar(tmp_path, "10/11/2026 09:06", forcar=True)
    monkeypatch.undo()
    minha.liberar()  # não é mais dona: não pode apagar a trava nova
    assert (tmp_path / trava.NOME_TRAVA).exists()
    monkeypatch.setattr(trava, "_maquina", lambda: "NOTEBOOK")
    assumida.liberar()
    assert not (tmp_path / trava.NOME_TRAVA).exists()


def test_trava_de_processo_morto_na_mesma_maquina_e_descartada(tmp_path):
    (tmp_path / trava.NOME_TRAVA).write_text(
        f'{{"maquina": "{trava._maquina()}", "pid": 0, "desde": "ontem"}}', encoding="utf-8"
    )
    trava.tomar(tmp_path, "agora").liberar()
    assert not (tmp_path / trava.NOME_TRAVA).exists()


def test_trava_de_processo_vivo_na_mesma_maquina_bloqueia(tmp_path):
    primeira = trava.tomar(tmp_path, "agora")
    with pytest.raises(trava.BancoEmUso) as erro:
        trava.tomar(tmp_path, "depois")
    assert erro.value.mesma_maquina
    primeira.liberar()


def test_trava_ilegivel_conta_como_outro_dono(tmp_path):
    (tmp_path / trava.NOME_TRAVA).write_text("", encoding="utf-8")
    with pytest.raises(trava.BancoEmUso):
        trava.tomar(tmp_path, "agora")


def test_conflitos_ignora_banco_backups_e_pre_migracao(tmp_path):
    for nome in [
        "money.sqlite",
        "money.antes-v2.sqlite",
        "money (1).sqlite",
        "money-DESKTOP-K9RROKI.sqlite",
        "outro.sqlite",
        "tema.toml",
    ]:
        (tmp_path / nome).write_bytes(b"")
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "money.2026-11-10-010101.sqlite").write_bytes(b"")
    achados = [p.name for p in trava.conflitos(tmp_path, "money.sqlite")]
    assert achados == ["money (1).sqlite", "money-DESKTOP-K9RROKI.sqlite"]


def test_main_recusa_com_conflito_e_com_trava_alheia(local, tmp_path, capsys, monkeypatch):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    (pasta / "money (1).sqlite").write_bytes(b"")
    assert main(["--dados", str(pasta)]) == 1
    assert "conflito" in capsys.readouterr().err
    (pasta / "money (1).sqlite").unlink()
    (pasta / trava.NOME_TRAVA).write_text(
        '{"maquina": "NOTEBOOK", "pid": 1, "desde": "hoje"}', encoding="utf-8"
    )
    assert main(["--dados", str(pasta)]) == 1
    assert "NOTEBOOK" in capsys.readouterr().err
    assert os.path.exists(pasta / trava.NOME_TRAVA)
