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
