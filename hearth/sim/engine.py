"""One simulated outage over synthetic patients: per-tick clocks, a policy's plan states, crews, and the run files.

The world is the same under every policy (outage, weather, buildings, crews). Policies differ in what they know and do:
  p0  manual phone tree: staff call the list in order; the unreachable go to a welfare-check queue; reached patients
      call their supplier when low, first come first served; nobody is moved.
  p3  Hearth: every dark patient with a verified phone is known at once and decided each tick (hearth.decision rules);
      the rest are UNREACHABLE until a crew checks; crews go to the highest risk weight per hour left.
use_buildings=False keeps the world but gives the planner default time constants and no refuge buildings.
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from hearth import store
from hearth.buildings.profile import service_minutes
from hearth.config import ASSUMPTIONS, ROOT, a
from hearth.contracts import BuildingProfile, run_id
from hearth.devices import drain
from hearth.metrics import at_risk, summarize
from hearth.outage import dark_mask, fraction_out
from hearth.planner import Crew, Flags, Need, assign
from hearth.population import km, load_population
from hearth.scenario import load
from hearth.sim.policies import MOVE, MOVED, NA, OWN, RES, RESTORED, STATES, UNR, WHY, decide_vec, hysteresis_vec
from hearth.temperature import step_indoor, unsafe_temp
from hearth.weather import hourly_weather


def policy_label(policy: str, flags: Flags) -> str:
    return policy + ("__nobld" if not flags.use_buildings else "") + ("__nomove" if not flags.allow_moves else "") + \
        ("__aid" if flags.mutual_aid else "")


def _iso(t) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _split(total: int, shares: list[float]) -> list[int]:
    """Largest-remainder split of `total` crews by supplier share."""
    raw = [total * s for s in shares]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: (out[i] - raw[i], i))[: total - sum(out)]:
        out[i] += 1
    return out


def hours_to_unsafe(indoor, temps, rhs, heat_tc, cold_tc, sens, dt) -> np.ndarray:
    """Hours until the home turns unsafe for this patient if it stays dark (0 if unsafe now, inf if not in the horizon)."""
    out = np.where(unsafe_temp(indoor, rhs[0], sens), 0.0, np.inf)
    x, dark = indoor, np.ones(len(indoor), bool)
    for j, (tc, rh) in enumerate(zip(temps, rhs), start=1):
        x = step_indoor(x, tc, dark, heat_tc, cold_tc, dt)
        out[np.isinf(out) & unsafe_temp(x, rh, sens)] = j * dt
    return out


def run(scenario: str, policy: str, seed: int, crews: int, flags: Flags = Flags(), out_root: Path | None = ROOT / "results") -> dict:
    """Simulate and return the summary; with out_root, also write out_root/<run_id>/ (meta, events, snapshots, summary,
    a copy of assumptions.yaml)."""
    assert policy in ("p0", "p3"), policy
    sc = load(scenario)
    dt, horizon = a("sim.tick_minutes") / 60, a("sim.horizon_h")
    ticks = pd.date_range(sc["start"], sc["end"], freq=f"{a('sim.tick_minutes')}min")
    hours = np.arange(len(ticks)) * dt
    ps = load_population(scenario, seed)
    n, idx_of = len(ps), {p.patient_id: i for i, p in enumerate(ps)}
    rng = np.random.default_rng([seed, 1])  # its own stream, apart from the population's

    # world
    f = fraction_out(scenario)
    r = np.array(sc["r"], float) if "r" in sc else rng.random(n)
    dark_all = dark_mask(r, f.reindex(ticks).interpolate(limit_direction="both"))
    w = hourly_weather(scenario)
    wx = (w.index - ticks[0]) / pd.Timedelta("1h")
    temp_out, rh_out = np.interp(hours, wx, w.temp_c), np.interp(hours, wx, w.rh)
    col = lambda k: np.array([getattr(p, k) for p in ps])  # noqa: E731
    lat, lon, use_rate, weight, backup = col("lat"), col("lon"), col("use_rate"), col("risk_weight"), col("backup_hours_on_hand")
    device, sens, supplier = np.array([p.device.value for p in ps]), col("temp_sensitive"), col("supplier_id")
    verified = col("phone_status") == "verified"
    profiles = {d["building_id"]: BuildingProfile.model_validate(d) for d in store.all("profile")}
    prof = [profiles.get(p.building_id) for p in ps]
    d_heat, d_cold = float(a("temperature.default_heat_tc_h")), float(a("temperature.default_cold_tc_h"))
    heat = np.array([q.heat_time_constant_h if q else d_heat for q in prof])
    cold = np.array([q.cold_time_constant_h if q else d_cold for q in prof])
    service_h = np.array([service_minutes(q, p.floor, False) if q else a("building.service_base_min") for q, p in zip(prof, ps)]) / 60
    # what the planner knows
    heat_b, cold_b = (heat, cold) if flags.use_buildings else (np.full(n, d_heat), np.full(n, d_cold))
    dests = [(la, lo) for la, lo, _ in a("planner.destinations")]
    if flags.use_buildings:  # surveyed hotels and senior housing can take a patient
        dests += [(q.lat, q.lon) for q in profiles.values() if any(k in str(q.property_type.value).lower() for k in ("hotel", "senior"))]
    dests = np.array(dests)
    dest = dests[np.argmin(km(lat[:, None], lon[:, None], dests[None, :, 0], dests[None, :, 1]), axis=1)]

    orgs = [f"s{i + 1}" for i in range(len(a("population.supplier_shares")))]
    depots = a("planner.depots")
    crew_orgs = [o for o, c in zip(orgs, _split(crews, a("population.supplier_shares"))) for _ in range(c)]
    fleet = [Crew(f"c{k + 1:02d}", o, *depots[o]) for k, o in enumerate(crew_orgs)]
    stock = {o: a("planner.stock_per_supplier") for o in orgs}

    # state
    state, streak = np.full(n, NA, np.int8), np.zeros(n, int)
    moved, ever_dark, prev_dark, has_job, zeroed = (np.zeros(n, bool) for _ in range(5))
    known = verified.copy() if policy == "p3" else np.zeros(n, bool)
    indoor = np.full(n, float(a("temperature.setpoint_c")))
    indoor_b = indoor.copy()
    since = np.full(n, np.nan)  # p0: when the patient's request entered the queue
    if policy == "p0":
        call_order = rng.permutation(n)
        unreachable = rng.random(n) < a("phone_tree.unreachable_rate")
        calls_per_tick = a("phone_tree.staff") * a("phone_tree.calls_per_staff_hour") * dt
        called = np.zeros(n, bool)
    risk = np.zeros((len(ticks), n), bool)
    device_h = temp_h = 0.0
    moves, active_jobs, events, snaps = 0, [], [], []
    every = sc.get("snapshot_every_ticks", a("sim.snapshot_every_ticks"))
    out = None
    if out_root is not None:
        out = Path(out_root) / run_id(scenario, policy_label(policy, flags), crews, seed)
        if (out / "meta.json").exists():
            shutil.rmtree(out)  # a previous copy of this same run
        (out / "snapshots").mkdir(parents=True)

    def ev(t, etype, i=None, **data):
        events.append({"t": _iso(t), "type": etype, "patient_id": None if i is None else ps[i].patient_id, "data": data})

    for k, t in enumerate(ticks):
        now, dark = hours[k], dark_all[k]
        # jobs that finish by now
        keep = []
        for done_h, job, i in active_jobs:
            if done_h > now:
                keep.append((done_h, job, i))
                continue
            has_job[i], since[i] = False, np.nan
            if job.kind == "delivery":
                backup[i] += a("planner.delivery_backup_h")
            elif job.kind == "ride" and dark[i]:  # power already back: the ride is not needed
                moved[i], moves = True, moves + 1
                ev(t, "moved", i, job_id=job.job_id)
            elif job.kind == "welfare_check":
                known[i] = True
            ev(t, "job_completed", i, job_id=job.job_id, kind=job.kind, org_id=job.org_id)
        active_jobs = keep

        for i in np.flatnonzero(dark & ~prev_dark):
            ev(t, "power_lost", int(i), zip=ps[i].zip)
        for i in np.flatnonzero(~dark & prev_dark):
            ev(t, "power_restored", int(i), zip=ps[i].zip)
        moved &= dark  # power back at home: a moved patient goes home
        ever_dark |= dark

        # clocks
        backup = drain(backup, use_rate, dark, moved, dt)
        indoor = step_indoor(indoor, temp_out[k], dark, heat, cold, dt)
        indoor_b = step_indoor(indoor_b, temp_out[k], dark, heat_b, cold_b, dt)
        hot = unsafe_temp(indoor, rh_out[k], sens)
        risk[k] = at_risk(backup, dark, moved, hot)
        empty = (backup <= 0) & dark & ~moved
        device_h, temp_h = device_h + empty.sum() * dt, temp_h + (hot & ~moved).sum() * dt
        for i in np.flatnonzero(empty & ~zeroed):
            ev(t, "backup_empty", int(i), device=device[i])
        zeroed |= empty

        # plan states
        new = np.where(ever_dark, RESTORED, NA).astype(np.int8)
        new[moved] = MOVED
        live = dark & ~moved
        hu = np.full(n, np.inf)
        if policy == "p0":
            reach = int((k + 1) * calls_per_tick) - int(k * calls_per_tick)
            done_calls = int(called.sum())
            batch = call_order[done_calls:done_calls + reach]
            called[batch] = True
            known[batch[~unreachable[batch]]] = True
            new[live & ~known] = UNR
            kn = live & known
            new[kn] = np.where(backup[kn] < a("decision.low_backup_h"), RES, OWN)
            want = np.where((new == RES) | (called & ~known), np.where(new == RES, 0, 2), -1)  # 0 delivery, 2 welfare check
            want[has_job] = -1
            since[(want >= 0) & np.isnan(since)] = now
        else:
            new[live & ~known] = UNR
            ix = np.flatnonzero(live & known)
            if ix.size:
                ahead = slice(k + 1, k + 1 + int(horizon / dt))
                hu[ix] = hours_to_unsafe(indoor_b[ix], temp_out[ahead], rh_out[ahead], heat_b[ix], cold_b[ix], sens[ix], dt) \
                    if temp_out[ahead].size else np.inf
                org_ok = {o: stock[o] > 0 and (o in crew_orgs) for o in orgs}
                any_ok = any(stock[o] > 0 for o in set(crew_orgs))
                deliver = (device[ix] != "home_dialysis") & (np.array([org_ok[s] for s in supplier[ix]]) | (flags.mutual_aid and any_ok))
                prop = decide_vec(device[ix], sens[ix], backup[ix], float(horizon), hu[ix] == 0, hu[ix] <= horizon,
                                  deliver, np.ones(ix.size, bool), flags.allow_moves)
                new[ix], streak[ix] = hysteresis_vec(state[ix], prop, streak[ix])
            want = np.select([new == RES, new == MOVE, new == UNR], [0, 1, 2], -1)
            want[has_job] = -1
        for i in np.flatnonzero(new != state):
            ev(t, "state_change", int(i), **{"from": STATES[state[i]].value, "to": STATES[new[i]].value, "why": WHY[int(new[i])]})
        state = new

        # crews
        free = sum(c.free_at_h <= now for c in fleet)
        cand = np.flatnonzero(want >= 0)
        if free and cand.size:
            if policy == "p0":
                order = np.lexsort((cand, since[cand]))
            else:
                left = np.where(want[cand] == 0, backup[cand], np.where(want[cand] == 1, np.minimum(backup[cand], hu[cand]),
                                                                         a("decision.low_backup_h")))  # silence: assume low
                order = np.lexsort((cand, -weight[cand] / np.maximum(left, 0.1)))
            cand = cand[order][: free * a("planner.candidates_per_free_crew")]  # shortcut: deeper needs wait a tick
            kinds = ("delivery", "ride", "welfare_check")
            needs = [Need(ps[i].patient_id, kinds[want[i]], supplier[i], weight[i],
                          float(backup[i] if want[i] == 0 else min(backup[i], hu[i]) if want[i] == 1 else a("decision.low_backup_h")),
                          lat[i], lon[i], service_h[i], float(since[i]) if policy == "p0" else now,
                          tuple(dest[i]) if want[i] == 1 else None) for i in cand]
            for job in assign(needs, fleet, stock, flags, now, fcfs=policy == "p0"):
                i = idx_of[job.patient_id]
                has_job[i] = True
                active_jobs.append((job.data["done_h"], job, i))
                eta = ticks[0] + pd.Timedelta(hours=job.data["done_h"])
                ev(t, "job_created", i, job_id=job.job_id, kind=job.kind, org_id=job.org_id, crew_id=job.data["crew_id"], eta=_iso(eta))
        prev_dark = dark

        if out is not None and k % every == 0:
            snap = {"t": _iso(t), "patients": [
                {"id": ps[i].patient_id, "lat": ps[i].lat, "lon": ps[i].lon, "device": device[i], "state": STATES[state[i]].value,
                 "backup_hours": round(float(backup[i]), 1), "indoor_temp_c": round(float(indoor[i]), 1),
                 "unpowered": bool(dark[i]), "building_id": ps[i].building_id} for i in range(n)],
                "crews": [{"crew_id": c.crew_id, "org_id": c.org_id, "lat": round(c.lat, 5), "lon": round(c.lon, 5),
                           "busy": bool(c.free_at_h > now)} for c in fleet],
                "depots": [{"supplier_id": o, "lat": depots[o][0], "lon": depots[o][1], "stock": stock[o]} for o in orgs]}
            (out / "snapshots" / f"{len(snaps)}.json").write_text(json.dumps(snap, separators=(",", ":")))
            snaps.append(_iso(t))

    rid = run_id(scenario, policy_label(policy, flags), crews, seed)
    summary = {"run_id": rid, **{k: float(v) for k, v in summarize(risk, weight, dt).items()}}
    if out is not None:
        (out / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        meta = {"run_id": rid, "scenario": scenario, "policy": policy_label(policy, flags), "crews": crews, "seed": seed,
                "flags": vars(flags), "ticks": snaps, "center": sc["center"], "patients": n, "synthetic": True,
                "label": sc.get("label"), "corrected_intervals": f.attrs["corrected"],
                "note": "simulated run over synthetic patients; outcomes are model outputs, not a count of lives saved"}
        (out / "meta.json").write_text(json.dumps(meta, indent=1))
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        shutil.copyfile(ASSUMPTIONS, out / "assumptions.yaml")
    return summary
