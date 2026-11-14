import pytest

from hearth.buildings.agent import survey


@pytest.fixture(autouse=True)
def fixtures(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))


@pytest.mark.live
def test_fixture_building_survey_reports_the_elevator_conflict():
    events = list(survey("B-SAMPLE", "x", 29.7604, -95.3698, use_cache=False))
    p = events[-1].data["profile"]
    assert p["error"] is None, p["error"]
    assert p["conflicts"] and p["floors"]["source"] == "costar" and p["roof_tone"]["source"] == "vexcel"
    assert any(e.kind == "todo" for e in events) and sum(e.kind == "subagent" for e in events) >= 3
    assert events[-1].t < 60


@pytest.mark.live
def test_building_without_a_scan_says_so():
    p = list(survey("B-NOSCAN", "x", 29.7530, -95.3600, use_cache=False))[-1].data["profile"]
    assert "matterport" in p["layers_missing"] and p["entrance_steps"]["source"] == "default" and p["error"] is None
