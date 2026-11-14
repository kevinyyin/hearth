import json
from pathlib import Path

import pytest

from hearth import store
from hearth.buildings import agent
from hearth.buildings.agent import survey, write_profile
from hearth.buildings.trace import to_trace

RECORDED_CHUNKS = json.loads((Path(__file__).parent / "recorded_chunks.json").read_text())


@pytest.fixture(autouse=True)
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("HEARTH_FIXTURES", "1")


def args(fields, missing="[]"):
    return {"building_id": "B", "fields_json": json.dumps(fields), "evidence_json": "[]", "conflicts_json": "[]", "layers_missing_json": missing}


def test_trace_maps_todos_subagents_and_files():
    events = [e for c in RECORDED_CHUNKS for e in to_trace(c, 0, 0)]
    kinds = [e.kind for e in events]
    assert {"todo", "subagent", "tool", "file", "profile"} <= set(kinds)
    assert {e.agent for e in events if e.kind == "subagent"} >= {"costar", "aerial", "interior"}


def test_write_profile_rejects_unsourced_field():
    out = write_profile.invoke(args({"floors": {"value": 8, "source": "guess", "confidence": 1}}))
    assert "error" in out and store.get("profile", "B") is None


def test_write_profile_rejects_a_default_that_carries_a_value():
    assert "error" in write_profile.invoke(args({"floors": {"value": 8, "source": "default", "confidence": 0}}))


def test_write_profile_rejects_unknown_field():
    assert "error" in write_profile.invoke(args({"pool": {"value": True, "source": "vexcel", "confidence": 1}}))


def test_write_profile_saves_a_finalized_profile():
    out = write_profile.invoke(args({"floors": {"value": 8, "source": "costar", "confidence": 0.9},
                                     "roof_tone": {"value": "dark", "source": "vexcel", "confidence": 0.7}}, '["matterport"]'))
    p = store.get("profile", "B")
    assert "saved" in out and p["floors"]["source"] == "costar" and p["heat_time_constant_h"] < 8.0
    assert p["layers_missing"] == ["matterport"] and p["step_free_entrance"]["source"] == "default"


class ExplodingGraph:
    def stream(self, *a, **k):
        raise RuntimeError("model unavailable")


def test_survey_always_ends_with_done_and_a_profile(monkeypatch):
    monkeypatch.setattr(agent, "build_surveyor", lambda model=None: ExplodingGraph())
    last = list(survey("B", "x", 0, 0, use_cache=False))[-1]
    assert last.kind == "done" and last.data["profile"]["error"] and last.data["profile"]["floors"]["source"] == "default"


def test_cached_profile_is_labeled_cached(monkeypatch):
    write_profile.invoke(args({"floors": {"value": 8, "source": "costar", "confidence": 0.9}}))
    monkeypatch.setattr(agent, "build_surveyor", lambda model=None: ExplodingGraph())
    events = list(survey("B", "x", 0, 0))
    assert len(events) == 1 and events[0].data["profile"]["cached"] is True


def test_a_failing_layer_is_reported_not_raised(monkeypatch, tmp_path):
    from hearth.buildings import tools
    monkeypatch.setattr(tools, "CACHE_ROOT", tmp_path)  # no cached layer files

    def boom(*a, **k):
        raise RuntimeError("429 Too Many Requests")
    monkeypatch.setattr(tools, "vexcel_attributes", boom)
    monkeypatch.setattr(tools, "matterport_rooms", boom)
    assert "unavailable" in agent.vexcel_attributes.invoke({"building_id": "B-SAMPLE"})
    assert "unavailable" in agent.matterport_rooms.invoke({"building_id": "B-SAMPLE"})


def test_cached_survey_fills_fields_added_after_it_was_stored(monkeypatch):
    from hearth.buildings.profile import default_profile, finalize
    old = finalize(default_profile("B", "x", 0, 0)).model_dump(mode="json")
    old.pop("unit_type")
    store.put("profile", "B", old)
    monkeypatch.setattr(agent, "build_surveyor", lambda model=None: ExplodingGraph())
    [done] = list(survey("B", "x", 0, 0))
    assert done.data["profile"]["unit_type"]["source"] == "default" and done.data["profile"]["cached"] is True
