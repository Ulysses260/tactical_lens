import sqlite3
from pathlib import Path

import pytest

from tactical_lens.db.connection import get_db_path, init_db


def test_get_db_path_env(monkeypatch, tmp_path):
    p = tmp_path / "override.db"
    monkeypatch.setenv("TACTICAL_LENS_DB", str(p))
    assert get_db_path() == p


def test_init_db_creates_db(tmp_path):
    db_file = tmp_path / "test.db"
    path = init_db(db_path=db_file)
    assert path.exists()
    # try connecting
    conn = sqlite3.connect(str(path))
    conn.close()
