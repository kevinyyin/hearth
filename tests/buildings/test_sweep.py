from bhelpers import profile

from hearth.buildings.__main__ import rank
from hearth.buildings.profile import finalize
from evals.run_buildings import score


def prof(building_id, heat):
    return finalize(profile(building_id)).model_copy(update={"heat_time_constant_h": heat})


def test_ranking_puts_fastest_heating_first():
    rows = rank([prof("B", heat=12.0), prof("A", heat=5.0)], patients_by_building={"A": 2, "B": 9})
    assert [r["building_id"] for r in rows] == ["A", "B"] and rows[0]["hours_to_unsafe_at_35c"] < rows[1]["hours_to_unsafe_at_35c"]
    assert rows[0]["patients"] == 2 and set(rows[0]["layers_missing"]) == {"costar", "vexcel", "matterport"}


def test_score_counts_right_wrong_unknowns_and_silent_fills():
    p = profile("B", floors=8, step_free=True, roof="dark")          # elevator_count left as default (unknown)
    labels = {"floors": "8", "step_free_entrance": "no", "roof_tone": "unknown", "elevator_count": "unknown", "entrance_steps": ""}
    s = score(p, labels)
    assert s["floors"] == "right" and s["step_free_entrance"] == "wrong"
    assert s["roof_tone"] == "silent_fill" and s["elevator_count"] == "right_unknown" and "entrance_steps" not in s
