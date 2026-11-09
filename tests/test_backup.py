import datetime as dt
import sqlite3

import pytest

from money_cli.armazenamento.banco import Banco
from money_cli.dominio.mes import Mes
from money_cli.dominio.tipos import NovoLancamento, Tipo
from money_cli.tela.app import MoneyApp


def test_backup_manual_gera_copia_nova_mantem_as_cinco_ultimas_e_restaura(tmp_path):
    b = Banco.abrir(tmp_path / "money.sqlite")
    conta = b.criar_conta("Itaú", "#8a2be2")
    hoje = dt.date(2026, 11, 1)
    agora = dt.datetime(2026, 11, 1, 10, 30, 5)
    try:
        b.inserir_lancamentos([NovoLancamento(hoje, "Café", 99, Tipo.DESPESA, conta.id)])
        primeiro = b.backup_manual(agora)
        assert primeiro.name == "money.2026-11-01-103005.sqlite"
        conteudo = primeiro.read_bytes()
        # Mesmo segundo: nome livre, sem sobrescrever a cópia anterior.
        b.inserir_lancamentos([NovoLancamento(hoje, "Pão", 500, Tipo.DESPESA, conta.id)])
        segundo = b.backup_manual(agora)
        assert segundo.name == "money.2026-11-01-103005-2.sqlite"
        assert primeiro.read_bytes() == conteudo
        # Cópia de pré-migração e arquivos de outro formato nunca entram na poda.
        migracao = tmp_path / "money.antes-v2.sqlite"
        migracao.write_bytes(b"migracao")
        diaria = tmp_path / "backups" / "money.2026-10-01.sqlite"
        diaria.write_bytes(b"formato antigo")
        for dias in range(1, 13):
            ultimo = b.backup_manual(agora + dt.timedelta(days=dias))
        copias = sorted((tmp_path / "backups").glob("money.2026-1*-*-*.sqlite"))
        assert len(copias) == 5
        assert copias[0].name == "money.2026-11-09-103005.sqlite"
        assert copias[-1] == ultimo
        assert migracao.exists() and diaria.exists()
        assert not list((tmp_path / "backups").glob(".backup-*"))
        restaurado = Banco.abrir(ultimo)
        try:
            assert restaurado.totais_do_mes(Mes(2026, 11)) == b.totais_do_mes(Mes(2026, 11))
        finally:
            restaurado.fechar()
    finally:
        b.fechar()


def test_falha_de_copia_nao_publica_nem_remove_backups(tmp_path, monkeypatch):
    b = Banco.abrir(tmp_path / "money.sqlite")
    try:
        b.backup_manual(dt.datetime(2026, 11, 1, 9, 0, 0))
        pasta = tmp_path / "backups"
        antes = {p.name: p.read_bytes() for p in pasta.iterdir()}

        def falhar(origem, destino):
            destino.write_bytes(b"parcial")
            raise sqlite3.OperationalError("disco cheio")

        monkeypatch.setattr("money_cli.armazenamento.banco.copiar_banco", falhar)
        with pytest.raises(OSError):
            b.backup_manual(dt.datetime(2026, 11, 2, 9, 0, 0))
        assert {p.name: p.read_bytes() for p in pasta.iterdir()} == antes
    finally:
        b.fechar()


def test_banco_em_memoria_nao_faz_backup(banco):
    assert banco.backup_manual() is None


async def test_app_nao_faz_backup_sozinho_e_tecla_b_faz(tmp_path, monkeypatch):
    b = Banco.abrir(tmp_path / "money.sqlite")
    app = MoneyApp(b)
    try:
        async with app.run_test() as piloto:
            await piloto.pause()
            assert not (tmp_path / "backups").exists()
            await piloto.press("b")
            assert len(list((tmp_path / "backups").glob("money.*.sqlite"))) == 1

            def falhar():
                raise OSError("sem espaço")

            monkeypatch.setattr(b, "backup_manual", falhar)
            await piloto.press("b")
            await piloto.press("right")
            assert app.mes == Mes.de(app.hoje).seguinte()
    finally:
        b.fechar()


def test_poda_ordena_sufixo_numerico_como_numero(tmp_path):
    b = Banco.abrir(tmp_path / "money.sqlite")
    agora = dt.datetime(2026, 11, 1, 10, 0, 0)
    try:
        nomes = [b.backup_manual(agora).name for _ in range(12)]
        restam = sorted(p.name for p in (tmp_path / "backups").iterdir())
        # As 5 últimas pedidas (-8 a -12) ficam; "-2" não vence "-10" por ordem de texto.
        assert restam == sorted(nomes[-5:])
        assert nomes[-1].endswith("-12.sqlite")
    finally:
        b.fechar()
