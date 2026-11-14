"""One SQLite table of JSON documents: docs(kind, id, json, updated_at). Path from HEARTH_DB."""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel


def _conn() -> sqlite3.Connection:
    path = Path(os.environ.get("HEARTH_DB", "data/hearth.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE IF NOT EXISTS docs (kind TEXT, id TEXT, json TEXT, updated_at REAL, PRIMARY KEY (kind, id))")
    return c


def put(kind: str, id: str, obj: BaseModel | dict) -> None:
    doc = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    with closing(_conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO docs VALUES (?, ?, ?, ?)", (kind, id, json.dumps(doc), time.time()))


def get(kind: str, id: str) -> dict | None:
    with closing(_conn()) as c:
        row = c.execute("SELECT json FROM docs WHERE kind = ? AND id = ?", (kind, id)).fetchone()
    return json.loads(row[0]) if row else None


def all(kind: str) -> list[dict]:
    """Oldest write first (a replaced doc moves to the end)."""
    with closing(_conn()) as c:
        rows = c.execute("SELECT json FROM docs WHERE kind = ? ORDER BY rowid", (kind,)).fetchall()
    return [json.loads(r[0]) for r in rows]
