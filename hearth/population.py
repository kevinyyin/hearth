"""Synthetic patients from emPOWER ZIP totals, a configured device mix, and homes inside ZCTA polygons.

Every patient is synthetic (`synthetic: True`): device type by ZIP is not public, so devices, backup, mobility and the
rest are drawn from config/assumptions.yaml by seed. Nothing here describes a real person.
"""
import json

import numpy as np
import pandas as pd

from hearth import store
from hearth.config import a
from hearth.contracts import Patient
from hearth.scenario import PROCESSED, load, processed

MASKED = 11  # emPOWER publishes any count from 1 to 11 as 11
DETAIL = {"oxygen": "concentrator", "ventilator": "home ventilator", "home_dialysis": "home dialysis machine"}


def km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (arrays broadcast)."""
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(np.subtract(lon2, lon1))
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def inside(x: np.ndarray, y: np.ndarray, rings: list[np.ndarray]) -> np.ndarray:
    """Even-odd ray cast over every ring (outer rings, holes, all parts): True where (x, y) is inside."""
    hit = np.zeros(len(x), bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        for ring in rings:
            x1, y1, x2, y2 = ring[:-1, 0, None], ring[:-1, 1, None], ring[1:, 0, None], ring[1:, 1, None]
            hit ^= np.logical_xor.reduce(((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1), axis=0)
    return hit


def _rings(geom: dict) -> list[np.ndarray]:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [np.asarray(r, float) for poly in polys for r in poly]


def _homes(rng, rings: list[np.ndarray], n: int) -> np.ndarray:
    """n uniform random (lon, lat) points inside the polygon, by rejection from its bounding box."""
    xy = np.concatenate(rings)
    out = np.empty((0, 2))
    while len(out) < n:
        pts = rng.uniform(xy.min(0), xy.max(0), size=(4 * n + 16, 2))
        out = np.vstack([out, pts[inside(pts[:, 0], pts[:, 1], rings)]])
    return out[:n]


def _zip_table(sc: dict, rng) -> tuple[list[str], np.ndarray, np.ndarray, dict]:
    """(zips, patients per ZIP, oxygen per ZIP, ZIP -> polygon rings)."""
    month = sc["empower_month"]
    d = pd.read_csv(processed(f"empower_{sc['name']}.csv"), dtype=str)
    total = d[f"{month}_Power_Dependent_Devices_DME"].astype(int).to_numpy()
    o2 = d[f"{month}_O2_Services_Any_DME"].astype(int).to_numpy()
    total = np.where(total == MASKED, rng.integers(1, MASKED + 1, len(total)), total)
    o2 = np.minimum(np.where(o2 == MASKED, rng.integers(1, MASKED + 1, len(o2)), o2), total)
    feats = json.loads(processed(f"zcta_{sc['name']}.geojson").read_text())["features"]
    return d.Zip_Code.tolist(), total, o2, {f["properties"]["zip"]: _rings(f["geometry"]) for f in feats}


def generate(scenario: str, seed: int) -> list[Patient]:
    sc, rng = load(scenario), np.random.default_rng(seed)
    if "patients" in sc:  # documented-case replays list their one patient explicitly
        return [Patient(**p) for p in sc["patients"]]
    zips, total, o2, shapes = _zip_table(sc, rng)
    mix = a("population.non_oxygen_mix")
    zip_, device, pid, homes = [], [], [], []
    for z, n, n_o2 in zip(zips, total, o2):
        rest = rng.multinomial(n - n_o2, list(mix.values()))
        device += ["oxygen"] * n_o2 + [k for k, m in zip(mix, rest) for _ in range(m)]
        zip_ += [z] * n
        pid += [f"SIM-{z}-{k:04d}" for k in range(n)]
        homes.append(_homes(rng, shapes[z], n))
    n = len(device)
    device, (lon, lat) = np.array(device), np.concatenate(homes).T

    def pick(m: dict):
        return rng.choice(list(m), size=n, p=list(m.values()))

    mobility, temp = pick(a("population.mobility_mix")), pick(a("population.temp_sensitive_mix"))
    bounds = np.array([a("population.backup_h")[d] for d in device], float)
    backup = rng.uniform(bounds[:, 0], bounds[:, 1])
    jejunal = rng.random(n) < a("population.feeding_jejunal_share")
    detail = np.array([DETAIL.get(d) or ("jejunal" if j else "gastric") for d, j in zip(device, jejunal)])
    weight = np.array([a(f"risk_weight.{d}" if d != "feeding_pump" else f"risk_weight.feeding_{x}") for d, x in zip(device, detail)])
    shares = a("population.supplier_shares")
    supplier = rng.choice([f"s{i + 1}" for i in range(len(shares))], size=n, p=shares)
    phone = np.where(rng.random(n) < a("population.reachable_phone_rate"), "verified", "unverified")
    profile = np.where(rng.random(n) < a("population.complete_profile_rate"), "complete", "partial")
    in_building = rng.random(n) < a("population.costar_building_share")

    # building residents move into the nearest surveyed CoStar building, so the engine can use its profile
    building, floor = np.full(n, None, object), np.ones(n, int)
    for prof in sorted(store.all("profile"), key=lambda p: p["building_id"]):
        if "hotel" in str(prof["property_type"]["value"]).lower():
            continue  # refuge candidates, not homes
        cand = np.flatnonzero(in_building & (building == None))  # noqa: E711 (object array)
        d = km(lat[cand], lon[cand], prof["lat"], prof["lon"])
        order = np.argsort(d, kind="stable")[: a("population.patients_per_building")]
        near = cand[order[d[order] <= a("population.building_match_km")]]
        floors = prof["floors"]["value"] if isinstance(prof["floors"]["value"], int) and prof["floors"]["value"] > 0 else 1
        building[near], lat[near], lon[near] = prof["building_id"], prof["lat"], prof["lon"]
        floor[near] = rng.integers(1, floors + 1, len(near))

    return [Patient(patient_id=pid[i], lat=round(float(lat[i]), 5), lon=round(float(lon[i]), 5), zip=zip_[i],
                    floor=int(floor[i]), device=device[i], device_detail=detail[i],
                    backup_hours_on_hand=round(float(backup[i]), 1), use_rate=1.0,  # backup is in hours at normal use
                    mobility=mobility[i], can_self_relocate=bool(mobility[i] == "walks"), temp_sensitive=temp[i],
                    risk_weight=float(weight[i]), supplier_id=supplier[i], building_id=building[i],
                    phone_status=phone[i], profile_status=profile[i]) for i in range(n)]


def load_population(scenario: str, seed: int) -> list[Patient]:
    """Synthetic patients for the scenario; also writes data/processed/patients_<scenario>_s<seed>.parquet."""
    ps = generate(scenario, seed)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([p.model_dump(mode="json") for p in ps]).to_parquet(PROCESSED / f"patients_{scenario}_s{seed}.parquet", index=False)
    return ps
