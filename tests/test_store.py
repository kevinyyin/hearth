from hearth import store
from hearth.contracts import Sourced


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    store.put("profile", "B1", {"x": 1})
    assert store.get("profile", "B1") == {"x": 1}
    assert store.get("profile", "nope") is None and len(store.all("profile")) == 1


def test_store_accepts_models_and_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    store.put("profile", "B1", Sourced(value=8, source="costar", confidence=0.9))
    store.put("profile", "B1", {"x": 2})
    assert store.all("profile") == [{"x": 2}]


def test_hearth_db_wins_over_a_database_url(tmp_path, monkeypatch):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("HEARTH_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")  # would fail if used
    store.put("profile", "B1", {"x": 1})
    assert store.get("profile", "B1") == {"x": 1}


import os  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.live
def test_postgres_roundtrip_and_order(monkeypatch):
    """Runs against HEARTH_DATABASE_URL (Supabase) only on purpose: pytest -m live tests/test_store.py."""
    import hearth.config  # noqa: F401 (loads .env)
    if not os.environ.get("HEARTH_DATABASE_URL"):
        pytest.skip("HEARTH_DATABASE_URL not set")
    monkeypatch.delenv("HEARTH_DB", raising=False)
    kind = f"_test_{uuid.uuid4().hex[:6]}"
    store.put(kind, "a", {"n": 1}); store.put(kind, "b", {"n": 2}); store.put(kind, "a", {"n": 3})
    assert store.get(kind, "a") == {"n": 3} and store.get(kind, "zz") is None
    assert store.all(kind) == [{"n": 2}, {"n": 3}]  # a replaced doc moves to the end
