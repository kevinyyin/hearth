"""Shelter sites: aerial search leads for when no refuge passes. Real ZCTA polygons, a faked Vexcel search."""
from contextlib import contextmanager

import pytest
from bhelpers import patient

from hearth import store
from hearth.buildings import refuge, tools
from hearth.config import a

HOME = (29.6876, -95.4601)        # ZIP 77096
BELLAIRE = (29.7050, -95.4600)    # ZIP 77401, about 1.9 km north
MEYERLAND = (29.6750, -95.4700)   # ZIP 77096 too
GULF = (28.5, -94.0)              # inside no ZIP polygon we hold


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(refuge, "MEMORY_FILE", str(tmp_path / "memories" / "dispatcher.md"))
    monkeypatch.setattr(tools, "costar_all", lambda: [])


def search(monkeypatch, by_phrase: dict):
    """Fake Vexcel: each phrase returns its own tiles; a phrase not listed returns none."""
    monkeypatch.setattr(tools, "vexcel_search", lambda lat, lon, half_m, text, limit: by_phrase.get(text, []))


def tile(at, score=0.2):
    return {"lat": at[0], "lon": at[1], "score": score}


def who():
    return patient(lat=HOME[0], lon=HOME[1], zip="77096", mobility="wheelchair_manual")


def test_tile_centers_reads_any_nesting_best_first():
    square = [[-95.4010, 29.7000], [-95.4010, 29.7006], [-95.4016, 29.7006], [-95.4016, 29.7000], [-95.4010, 29.7000]]
    j = {"features": [{"properties": {"score": 0.18}, "geometry": {"type": "Polygon", "coordinates": [square]}},
                      {"properties": {"score": 0.25}, "geometry": {"type": "MultiPolygon", "coordinates": [[square]]}},
                      {"properties": {"score": 0.30}, "geometry": {"type": "Polygon", "coordinates": []}}]}
    assert tools.tile_centers(j) == [{"lat": 29.7003, "lon": -95.4013, "score": 0.25}, {"lat": 29.7003, "lon": -95.4013, "score": 0.18}]
    assert tools.tile_centers({}) == []


def test_fixtures_search_no_aerial_tiles():
    assert tools.vexcel_search(*HOME, 3000, "church with large parking lot", 5) == []


def test_zip_at_agrees_with_the_simulations_numpy_version():
    import json

    from hearth import population
    shapes = {f["properties"]["zip"]: population._rings(f["geometry"]) for f in json.loads(refuge.ZCTA_FILE.read_text())["features"]}
    points = [HOME, BELLAIRE, MEYERLAND, GULF] + [(29.60 + i * 0.031, -95.60 + k * 0.037) for i in range(8) for k in range(8)]
    assert [refuge.zip_at(*p) for p in points] == [population.zip_at(*p, shapes) for p in points]
    assert (refuge.zip_at(*HOME), refuge.zip_at(*BELLAIRE), refuge.zip_at(*GULF)) == ("77096", "77401", None)


def test_a_site_in_a_dark_or_unknown_zip_is_dropped(monkeypatch):
    phrase = a("shelter.phrases")[0]
    search(monkeypatch, {phrase: [tile(MEYERLAND, 0.30), tile(GULF, 0.29), tile(BELLAIRE, 0.18)]})
    [site] = refuge.shelter_sites(who(), {"77096"})
    assert (site["lat"], site["lon"], site["zip"]) == (*BELLAIRE, "77401")
    assert site["looks_like"] == phrase and site["km"] == 1.9 and site["score"] == 0.18
    assert site["costar"] is None and site["caveat"] == refuge.SHELTER_CAVEAT and "not verified" in site["caveat"]
    assert refuge.shelter_sites(who(), {"77096", "77401"}) == []


def test_tiles_of_one_place_merge_and_the_best_match_names_it(monkeypatch):
    gym, church = a("shelter.phrases")[:2]
    next_tile = (BELLAIRE[0] + 0.0006, BELLAIRE[1])  # the next tile north, about 66 m away
    search(monkeypatch, {gym: [tile(BELLAIRE, 0.18)], church: [tile(next_tile, 0.24)]})
    [site] = refuge.shelter_sites(who(), {"77096"})
    assert site["looks_like"] == church and (site["lat"], site["lon"]) == next_tile


def test_nearest_first_and_only_the_top_few(monkeypatch):
    north = [(round(29.693 + i * 0.004, 3), BELLAIRE[1]) for i in range(a("shelter.max_sites") + 2)]  # 445 m apart, all in 77401
    search(monkeypatch, {a("shelter.phrases")[0]: [tile(p, 0.2 + i / 100) for i, p in enumerate(north)]})
    sites = refuge.shelter_sites(who(), {"77096"})
    assert [(s["lat"], s["lon"]) for s in sites] == north[: a("shelter.max_sites")]
    assert [s["km"] for s in sites] == sorted(s["km"] for s in sites)


def test_a_site_joins_the_costar_record_beside_it_and_no_farther(monkeypatch):
    rec = {"building_id": "77", "name": "Bellaire Hall", "address": "1 Hall St, Bellaire, TX 77401", "zip": "77401", "property_type": "specialty",
           "floors": 1, "surface_spaces": 120, "lot_acres": 2.5, "lat": BELLAIRE[0] + 0.0004, "lon": BELLAIRE[1], "elevator_count": None}
    far = rec | {"building_id": "78", "name": "Far Hall", "lat": BELLAIRE[0] + 0.01}
    monkeypatch.setattr(tools, "costar_all", lambda: [far, rec, {"building_id": "old-fixture", "property_type": "hotel"}])
    search(monkeypatch, {a("shelter.phrases")[0]: [tile(BELLAIRE)]})
    [site] = refuge.shelter_sites(who(), {"77096"})
    assert site["costar"] == {"building_id": "77", "name": "Bellaire Hall", "property_type": "specialty", "floors": 1,
                              "surface_spaces": 120, "lot_acres": 2.5, "m": 44}
    monkeypatch.setattr(tools, "costar_all", lambda: [far])
    assert refuge.shelter_sites(who(), {"77096"})[0]["costar"] is None


class FakeGraph:
    """Stands in for the model: it calls the shelter tool, as the prompt tells it to, and proposes nothing."""
    said = None

    def stream(self, *args, **kw):
        FakeGraph.said = refuge.search_shelter_sites.invoke({"patient_id": "p1"})
        return iter(())


@contextmanager
def fake_session():
    yield FakeGraph()


def test_sites_reach_the_dispatcher_on_the_done_event_from_code(monkeypatch):
    monkeypatch.setattr(refuge, "_graph_session", fake_session)
    search(monkeypatch, {a("shelter.phrases")[0]: [tile(BELLAIRE)]})
    last = list(refuge.propose(who(), {"77096"}))[-1]
    assert last.kind == "done" and last.data["error"] is None
    assert [s["zip"] for s in last.data["shelter_sites"]] == ["77401"]
    assert "1 possible shelter site" in last.text and "none confirmed" in last.text
    assert "77401" not in FakeGraph.said and "29.7" not in FakeGraph.said  # the model is told a count, never the facts
    assert store.all("proposal") == [] and store.all("call") == [] and store.all("message") == []  # leads only: nothing to approve, nobody called
    last = list(refuge.propose(who(), {"77096", "77401"}))[-1]  # the one match is in a dark ZIP now
    assert "found no shelter site" in last.text and "shelter_sites" not in last.data


def test_a_run_that_never_searched_says_what_it_said_before(monkeypatch):
    @contextmanager
    def idle_session():
        yield type("G", (), {"stream": lambda self, *a, **k: iter(())})()
    monkeypatch.setattr(refuge, "_graph_session", idle_session)
    refuge._sites["p1"] = [{"stale": True}]  # left by an earlier run
    last = list(refuge.propose(who(), {"77096"}))[-1]
    assert last.text == "no eligible refuge found; a dispatcher should decide" and "shelter_sites" not in last.data


def test_a_failed_search_is_reported_not_raised_and_shows_no_site(monkeypatch):
    monkeypatch.setattr(refuge, "_graph_session", fake_session)

    def boom(*args):
        raise RuntimeError("429 Too Many Requests")
    monkeypatch.setattr(tools, "vexcel_search", boom)
    last = list(refuge.propose(who(), {"77096"}))[-1]
    assert "unavailable" in FakeGraph.said and "shelter_sites" not in last.data and last.data["error"] is None


def test_without_the_zip_polygons_every_site_is_dropped_never_guessed_outside(monkeypatch, tmp_path):
    monkeypatch.setattr(refuge, "_graph_session", fake_session)
    monkeypatch.setattr(refuge, "ZCTA_FILE", tmp_path / "missing.geojson")
    monkeypatch.setattr(refuge, "_zip_rings", None)
    search(monkeypatch, {a("shelter.phrases")[0]: [tile(BELLAIRE)]})
    last = list(refuge.propose(who(), {"77096"}))[-1]
    assert "unavailable" in FakeGraph.said and "shelter_sites" not in last.data


def test_the_agent_has_the_tool_and_is_told_when_to_use_it():
    assert "search_shelter_sites" in refuge.SYSTEM and refuge.search_shelter_sites in refuge.TOOLS
