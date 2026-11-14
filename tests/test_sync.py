"""Synced data folder (D38): configuration, lock between computers, conflicts."""

import os

import pytest

from kotsu.__main__ import main
from kotsu.storage import lock, paths
from kotsu.storage.database import Database


@pytest.fixture
def local(tmp_path, monkeypatch):
    folder = tmp_path / "local"
    monkeypatch.delenv("KOTSU_DATA", raising=False)
    monkeypatch.setenv("APPDATA", str(folder))
    monkeypatch.setenv("XDG_DATA_HOME", str(folder))
    return folder / "kotsu"


def test_configured_folder_counts_and_env_var_wins(local, tmp_path, monkeypatch):
    assert paths.data_folder() == local
    drive = tmp_path / "drive" / 'Kotsu "x"\\y'
    paths.save_configured_folder(drive)
    assert paths.data_folder() == drive
    assert paths.backups_folder(drive) == local / "backups"
    monkeypatch.setenv("KOTSU_DATA", str(tmp_path / "other"))
    assert paths.data_folder() == tmp_path / "other"
    assert paths.backups_folder(tmp_path / "other") is None
    monkeypatch.delenv("KOTSU_DATA")
    paths.save_configured_folder(None)
    assert paths.data_folder() == local


def test_old_install_folder_and_pasta_dados_key_still_work(local, tmp_path):
    legacy = local.parent / paths._OLD_FOLDER
    legacy.mkdir(parents=True)
    drive = tmp_path / "drive"
    (legacy / paths.CONFIG_NAME).write_text(f'pasta_dados = "{drive.as_posix()}"\n', "utf-8")
    (legacy / "backups").mkdir()
    assert paths.data_folder() == drive
    assert local.is_dir() and not legacy.exists()
    assert (local / "backups").is_dir()


def test_unreadable_config_falls_back_to_default(local):
    local.mkdir(parents=True)
    (local / paths.CONFIG_NAME).write_text("this is not toml [[[", encoding="utf-8")
    assert paths.data_folder() == local


def test_configuring_copies_the_database_and_backup_goes_to_local_folder(local, tmp_path):
    db = Database.open(paths.database_file())
    db.create_account("Nubank", "#ff00ff")
    db.close()
    drive = tmp_path / "drive"

    assert main(["--data-folder", str(drive)]) == 0
    assert paths.data_folder() == drive.resolve()
    new = Database.open(paths.database_file(), paths.backups_folder(drive.resolve()))
    assert [a.name for a in new.list_accounts()] == ["Nubank"]
    copy = new.manual_backup()
    new.close()
    assert copy.parent == local / "backups"
    assert not (drive / "backups").exists()


def test_configuring_refuses_when_both_sides_have_a_database(local, tmp_path, capsys):
    Database.open(paths.database_file()).close()
    drive = tmp_path / "drive"
    Database.open(paths.database_file(drive)).close()
    assert main(["--data-folder", str(drive)]) == 1
    assert "does not join" in capsys.readouterr().err
    assert paths.configured_folder() is None


def test_lock_blocks_another_computer_and_force_takes_over(tmp_path, monkeypatch):
    mine = lock.acquire(tmp_path, "10/11/2026 09:00")
    monkeypatch.setattr(lock, "_machine", lambda: "NOTEBOOK")
    with pytest.raises(lock.DatabaseInUse) as error:
        lock.acquire(tmp_path, "10/11/2026 09:05")
    assert not error.value.same_machine
    assert "10/11/2026 09:00" in str(error.value)
    taken = lock.acquire(tmp_path, "10/11/2026 09:06", force=True)
    monkeypatch.undo()
    mine.release()  # no longer the owner: must not delete the new lock
    assert (tmp_path / lock.LOCK_NAME).exists()
    monkeypatch.setattr(lock, "_machine", lambda: "NOTEBOOK")
    taken.release()
    assert not (tmp_path / lock.LOCK_NAME).exists()


def test_lock_from_a_dead_process_on_the_same_machine_is_discarded(tmp_path):
    (tmp_path / lock.LOCK_NAME).write_text(
        f'{{"machine": "{lock._machine()}", "pid": 0, "since": "yesterday"}}', encoding="utf-8"
    )
    lock.acquire(tmp_path, "now").release()
    assert not (tmp_path / lock.LOCK_NAME).exists()


def test_old_kotsu_trava_from_another_computer_still_blocks(tmp_path):
    (tmp_path / lock.LEGACY_LOCK_NAME).write_text(
        '{"maquina": "NOTEBOOK", "pid": 1, "desde": "hoje"}', encoding="utf-8"
    )
    with pytest.raises(lock.DatabaseInUse) as error:
        lock.acquire(tmp_path, "now")
    assert error.value.machine == "NOTEBOOK" and error.value.since == "hoje"
    lock.acquire(tmp_path, "now", force=True).release()
    assert not (tmp_path / lock.LEGACY_LOCK_NAME).exists()


def test_lock_from_a_live_process_on_the_same_machine_blocks(tmp_path):
    first = lock.acquire(tmp_path, "now")
    with pytest.raises(lock.DatabaseInUse) as error:
        lock.acquire(tmp_path, "later")
    assert error.value.same_machine
    first.release()


def test_unreadable_lock_counts_as_another_owner(tmp_path):
    (tmp_path / lock.LOCK_NAME).write_text("", encoding="utf-8")
    with pytest.raises(lock.DatabaseInUse):
        lock.acquire(tmp_path, "now")


def test_conflicts_ignore_database_backups_and_pre_migration(tmp_path):
    for name in [
        "kotsu.sqlite",
        "kotsu.antes-v2.sqlite",
        "kotsu.before-v4.sqlite",
        "kotsu (1).sqlite",
        "kotsu-DESKTOP-ABC123.sqlite",
        "other.sqlite",
        "theme.toml",
    ]:
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "kotsu.2026-11-10-010101.sqlite").write_bytes(b"")
    found = [p.name for p in lock.conflicts(tmp_path, "kotsu.sqlite")]
    assert found == ["kotsu (1).sqlite", "kotsu-DESKTOP-ABC123.sqlite"]


def test_main_refuses_with_conflict_and_with_someone_elses_lock(local, tmp_path, capsys):
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "kotsu (1).sqlite").write_bytes(b"")
    assert main(["--data", str(folder)]) == 1
    assert "conflicted" in capsys.readouterr().err
    (folder / "kotsu (1).sqlite").unlink()
    (folder / lock.LOCK_NAME).write_text(
        '{"machine": "NOTEBOOK", "pid": 1, "since": "today"}', encoding="utf-8"
    )
    assert main(["--data", str(folder)]) == 1
    assert "NOTEBOOK" in capsys.readouterr().err
    assert os.path.exists(folder / lock.LOCK_NAME)


def test_old_database_names_are_renamed_without_losing_data(local, tmp_path):
    drive = tmp_path / "drive"
    db = Database.open(drive / "kotsu.sqlite")
    db.create_account("Nubank", "#ff00ff")
    db.close()
    old = paths._OLD_PREFIX
    (drive / "kotsu.sqlite").rename(drive / f"{old}.sqlite")
    (drive / f"{old}.before-v4.sqlite").write_bytes(b"x")
    (drive / "backups").mkdir()
    (drive / "backups" / f"{old}.2026-11-10-010101.sqlite").write_bytes(b"x")
    (drive / f"{old} (1).sqlite").write_bytes(b"x")
    (drive / f"{old}-notes.txt").write_bytes(b"x")  # not a database: left alone
    file = paths.database_file(drive)
    assert file == drive / "kotsu.sqlite"
    names = sorted(p.name for p in drive.iterdir())
    assert names == [
        "backups",
        "kotsu (1).sqlite",
        "kotsu.before-v4.sqlite",
        "kotsu.sqlite",
        f"{old}-notes.txt",
    ]
    assert [p.name for p in (drive / "backups").iterdir()] == ["kotsu.2026-11-10-010101.sqlite"]
    assert lock.conflicts(drive, file.name) == [drive / "kotsu (1).sqlite"]
    db = Database.open(file)
    assert [a.name for a in db.list_accounts()] == ["Nubank"]
    db.close()


def test_old_name_never_overwrites_the_new_database(local, tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "kotsu.sqlite").write_bytes(b"new")
    (folder / f"{paths._OLD_PREFIX}.sqlite").write_bytes(b"old")
    paths.database_file(folder)
    assert (folder / "kotsu.sqlite").read_bytes() == b"new"
    assert (folder / f"{paths._OLD_PREFIX}.sqlite").read_bytes() == b"old"
