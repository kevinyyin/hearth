"""One table of JSON documents: docs(kind, id, json, updated_at).

HEARTH_DB (a SQLite file) wins when set, which keeps tests on throwaway files; otherwise HEARTH_DATABASE_URL (Postgres,
e.g. Supabase) when set, so the hosted API keeps state between requests; otherwise data/hearth.db.
"""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel

_pg_conns: dict = {}  # one open connection per database URL in this process: opening one costs about 150 ms


def postgres_url() -> str | None:
    return None if os.environ.get("HEARTH_DB") else os.environ.get("HEARTH_DATABASE_URL")


def _pg(url: str, sql: str, params: tuple = ()):
    """Runs one statement on this process's connection (psycopg connections are thread-safe); a dropped connection
    is replaced once. Every statement here is a read or an upsert, so running it again is safe."""
    import psycopg

    for attempt in (0, 1):
        c = _pg_conns.get(url)
        if c is None or c.closed or c.broken:
            c = psycopg.connect(url, autocommit=True, prepare_threshold=None)  # no prepared statements: poolers reject them
            c.execute("CREATE TABLE IF NOT EXISTS docs (kind text, id text, json jsonb, updated_at double precision, "
                      "seq bigserial, PRIMARY KEY (kind, id))")
            _pg_conns[url] = c
        try:
            return c.execute(sql, params)
        except psycopg.OperationalError:
            c.close()
            if attempt:
                raise


def _conn() -> sqlite3.Connection:
    path = Path(os.environ.get("HEARTH_DB", "data/hearth.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE IF NOT EXISTS docs (kind TEXT, id TEXT, json TEXT, updated_at REAL, PRIMARY KEY (kind, id))")
    return c


def put(kind: str, id: str, obj: BaseModel | dict) -> None:
    doc = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    if url := postgres_url():
        from psycopg.types.json import Jsonb

        # a replaced doc takes a new seq, so all() keeps "oldest write first"
        _pg(url, "INSERT INTO docs (kind, id, json, updated_at) VALUES (%s, %s, %s, %s) ON CONFLICT (kind, id) DO UPDATE "
                 "SET json = excluded.json, updated_at = excluded.updated_at, seq = nextval(pg_get_serial_sequence('docs', 'seq'))",
            (kind, id, Jsonb(doc), time.time()))
        return
    with closing(_conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO docs VALUES (?, ?, ?, ?)", (kind, id, json.dumps(doc), time.time()))


def get(kind: str, id: str) -> dict | None:
    if url := postgres_url():
        row = _pg(url, "SELECT json FROM docs WHERE kind = %s AND id = %s", (kind, id)).fetchone()
        return row[0] if row else None
    with closing(_conn()) as c:
        row = c.execute("SELECT json FROM docs WHERE kind = ? AND id = ?", (kind, id)).fetchone()
    return json.loads(row[0]) if row else None


def all(kind: str) -> list[dict]:
    """Oldest write first (a replaced doc moves to the end)."""
    if url := postgres_url():
        return [r[0] for r in _pg(url, "SELECT json FROM docs WHERE kind = %s ORDER BY seq", (kind,)).fetchall()]
    with closing(_conn()) as c:
        rows = c.execute("SELECT json FROM docs WHERE kind = ? ORDER BY rowid", (kind,)).fetchall()
    return [json.loads(r[0]) for r in rows]
