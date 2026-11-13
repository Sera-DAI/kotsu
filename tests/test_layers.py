"""The layers rule, and proof that the test catches a deliberate violation."""

import shutil

import pytest

import layers


def test_current_code_respects_the_layers():
    assert layers.check() == []


@pytest.fixture
def copy(tmp_path):
    target = tmp_path / "kotsu"
    shutil.copytree(layers.DEFAULT_ROOT, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


@pytest.mark.parametrize(
    ("file", "line", "forbidden"),
    [
        ("domain/month.py", "from kotsu.ui.app import KotsuApp", "kotsu.ui.app"),
        ("domain/month.py", "import kotsu.storage.database", "kotsu.storage"),
        ("domain/models.py", "import sqlite3", "sqlite3"),
        ("domain/models.py", "from pathlib import Path", "pathlib"),
        ("domain/totals.py", "from ..ui import colors", "kotsu.ui"),
        ("storage/database.py", "from kotsu.ui import app", "kotsu.ui"),
        ("storage/paths.py", "from textual.app import App", "textual.app"),
        ("ui/app.py", "import sqlite3", "sqlite3"),
    ],
)
def test_injected_violation_is_detected(copy, file, line, forbidden):
    target = copy / file
    target.write_text(target.read_text(encoding="utf-8") + f"\n{line}\n", encoding="utf-8")
    violations = layers.check(copy)
    assert len(violations) >= 1
    assert all(v.file == target for v in violations)
    assert any(v.imports.startswith(forbidden) for v in violations)


def test_command_line_fails_with_violation(copy, capsys):
    (copy / "domain" / "new.py").write_text("import kotsu.ui\n", encoding="utf-8")
    assert layers.main([str(copy)]) == 1
    assert "violation" in capsys.readouterr().out
