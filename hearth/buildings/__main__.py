"""python -m hearth.buildings sweep [--limit N] : survey every building with a registered patient and rank which
becomes dangerous first ("switch it on Monday"). Writes data/processed/building_ranking.json.
python -m hearth.buildings bulk [--limit N] : records-only profiles (CoStar + Vexcel, no model) for every Houston home
and refuge building, so the simulation can use building data county-wide."""
import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from hearth import store
from hearth.buildings import tools
from hearth.buildings.agent import survey
from hearth.buildings.profile import hours_to_unsafe
from hearth.config import ROOT
from hearth.contracts import BuildingProfile

PATIENTS_FILE = ROOT / "data" / "processed" / "patients_beryl_2024_s1.parquet"
RANKING_FILE = ROOT / "data" / "processed" / "building_ranking.json"


def rank(profiles: list[BuildingProfile], patients_by_building: dict[str, int]) -> list[dict]:
    rows = [{"building_id": p.building_id, "address": p.address, "heat_time_constant_h": p.heat_time_constant_h,
             "hours_to_unsafe_at_35c": round(hours_to_unsafe(p.heat_time_constant_h, 35.0), 2),
             "patients": patients_by_building.get(p.building_id, 0), "layers_missing": p.layers_missing, "method": p.method}
            for p in profiles]
    return sorted(rows, key=lambda r: (r["hours_to_unsafe_at_35c"], -r["patients"]))


def patients_by_building() -> dict[str, int]:
    """Registered patients per building from the simulation's patients file; empty until lane S writes it."""
    if not PATIENTS_FILE.exists():
        return {}
    import pandas as pd

    ids = pd.read_parquet(PATIENTS_FILE, columns=["building_id"])["building_id"].dropna()
    return dict(Counter(ids))


def _survey_one(building_id: str) -> None:
    rec = tools.costar_record(building_id)
    for _ in survey(building_id, rec["address"], rec["lat"], rec["lon"]):  # cache first; a done event always ends it
        pass


def sweep(limit: int | None) -> list[dict]:
    counts = patients_by_building()
    # without the patients file, sweep the building types patients live in
    targets = sorted(counts, key=counts.get, reverse=True) or [
        r["building_id"] for r in tools.costar_all() if r["property_type"] in ("multifamily", "senior_housing")]
    surveyed = {p["building_id"] for p in store.all("profile") if p.get("method", "agent") == "agent"}
    todo = [b for b in targets[:limit] if b not in surveyed and tools.costar_record(b)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_survey_one, todo))
    profiles = [BuildingProfile.model_validate(p) for p in store.all("profile") if p["building_id"] in set(targets[:limit])]
    rows = rank(profiles, counts)
    RANKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    RANKING_FILE.write_text(json.dumps(rows, indent=1))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["sweep", "bulk"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if args.command == "bulk":
        from hearth.buildings.bulk import bulk

        print(bulk(args.limit))
        raise SystemExit
    rows = sweep(args.limit)
    print(f"ranked {len(rows)} buildings -> {RANKING_FILE}")
    for r in rows[:10]:
        print(f"  {r['hours_to_unsafe_at_35c']:5.1f} h  {r['building_id']:>10}  patients={r['patients']}  missing={r['layers_missing']}")
