"""
SQLite 连接与初始化
默认路径：项目根目录下 data/tactical_lens.db
可通过环境变量 TACTICAL_LENS_DB 覆盖
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator, Optional

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db_path() -> Path:
    env = os.environ.get("TACTICAL_LENS_DB")
    if env:
        return Path(env)
    # 默认：仓库根 / data /
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "tactical_lens.db"


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> Path:
    """执行 schema.sql，返回数据库路径"""
    path = db_path or get_db_path()
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(path) as conn:
        conn.executescript(schema)
    return path
