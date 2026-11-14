"""Records-only building profiles for every Houston home and refuge in the CoStar extract: CoStar fields plus Vexcel
attributes, no model call. They let the simulation use building data county-wide; the live agent survey stays the deep
read and is labeled differently (`method="fields"` here, `"agent"` there).

python -m hearth.buildings bulk [--limit N]
"""
from concurrent.futures import ThreadPoolExecutor

from hearth import store
from hearth.buildings import tools
from hearth.buildings.profile import default_profile, finalize
from hearth.config import a
from hearth.contracts import BuildingProfile, Evidence, Sourced

TYPES = ("multifamily", "senior_housing", "hotel")


def profile_from_fields(rec: dict, attrs: dict | None) -> BuildingProfile:
    conf = a("building_records.costar_confidence")
    upd = {f: Sourced(value=rec[f], source="costar", confidence=conf)
           for f in ("floors", "units", "year_built", "construction", "property_type", "elevator_count") if rec.get(f) is not None}
    evidence = []
    if "elevator_count" in upd:
        evidence.append(Evidence(field="elevator_count", layer="costar", ref=rec["building_id"], note=rec["elevator_note"]))
        if rec["elevator_note"] != "passenger elevators listed":  # "at least one" or a walk-up flag: inferred, not counted
            upd["elevator_count"] = upd["elevator_count"].model_copy(update={"confidence": a("building_records.costar_inferred_confidence")})
    if attrs:
        if attrs.get("tree_cover_fraction") is not None:
            upd["tree_cover_fraction"] = Sourced(value=attrs["tree_cover_fraction"], source="vexcel", confidence=conf)
        tone = a("building_records.roof_tone_by_material").get(str(attrs.get("roof_material")).lower())
        if tone:
            upd["roof_tone"] = Sourced(value=tone, source="vexcel", confidence=a("building_records.roof_tone_confidence"))
            evidence.append(Evidence(field="roof_tone", layer="vexcel", ref="property/extract",
                                     note=f"from roof material class '{attrs['roof_material']}' via a table, not a vision read"))
    missing = (["vexcel"] if not attrs else []) + ["matterport"]  # unit interiors need the agent's scan read
    base = default_profile(rec["building_id"], rec["address"], rec["lat"], rec["lon"])
    return finalize(base.model_copy(update={**upd, "evidence": evidence, "layers_missing": missing, "method": "fields"}))


def _one(rec: dict) -> str:
    try:
        attrs, _ = tools.cached(rec["building_id"], "vexcel", lambda: tools.vexcel_attributes(rec["lat"], rec["lon"]))
    except Exception:  # Vexcel down or rate-limited past backoff: the profile records Vexcel as missing
        attrs = None
    store.put("profile", rec["building_id"], profile_from_fields(rec, attrs))
    return "vexcel" if attrs else "no-vexcel"


def bulk(limit: int | None = None, workers: int = 6) -> dict:
    """Store a records-only profile for each building that has no agent survey yet. Vexcel responses are cached."""
    agent_done = {p["building_id"] for p in store.all("profile") if p.get("method", "agent") == "agent"}
    todo = [r for r in tools.costar_all() if r["property_type"] in TYPES and r["building_id"] not in agent_done][:limit]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(_one, todo))
    return {"stored": len(outcomes), "with_vexcel": outcomes.count("vexcel"), "skipped_agent_surveyed": len(agent_done)}
