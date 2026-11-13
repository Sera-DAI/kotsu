import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


@pytest.fixture
def db():
    from kotsu.storage.database import Database

    d = Database.in_memory()
    yield d
    d.close()
