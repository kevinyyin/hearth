from bhelpers import profile

from hearth.buildings.brief import access_brief
from hearth.buildings.profile import default_profile, finalize
from hearth.contracts import Evidence


def profile_with_evidence():
    p = profile(step_free=True, door_w=0.9, stair_w=1.1, van="curb loading zone, north side", floors=8)
    p.evidence = [
        Evidence(field="floors", layer="costar", ref="costar", note="8 stories"),
        Evidence(field="van_dropoff", layer="vexcel", ref="vexcel.png", note="yellow curb on the north side"),
        Evidence(field="step_free_entrance", layer="matterport", ref="pano-side", note="side door, level threshold"),
        Evidence(field="stair_width_m", layer="matterport", ref="pano-stair", note="main stairs, handrail one side"),
    ]
    return finalize(p)


def test_brief_never_invents_layout():
    b = access_brief(finalize(default_profile("B", "x", 0, 0)))
    assert b.route == [] and b.entrance is None and b.stop_at is None and b.widths is None and b.frames == []
    assert "matterport" in b.missing and "vexcel" in b.missing


def test_brief_uses_scan_evidence():
    b = access_brief(profile_with_evidence())
    assert b.entrance and "side door" in b.entrance and b.stop_at and "0.9" in b.widths
    assert b.frames and all(f.layer in ("matterport", "vexcel") for f in b.frames)
    assert len(b.route) == 2 and b.missing == []
