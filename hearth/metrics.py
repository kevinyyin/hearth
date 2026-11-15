"""Hours at risk: device out of backup in a dark home, or home temperature unsafe, and not moved."""
import numpy as np


def at_risk(backup_h, dark, moved, temp_unsafe) -> np.ndarray:
    return (((backup_h <= 0) & dark) | temp_unsafe) & ~moved


def summarize(risk_matrix, weights, dt_h) -> dict:
    return {"risk_hours_unweighted": risk_matrix.sum() * dt_h, "risk_hours_weighted": (risk_matrix * weights).sum() * dt_h}


def sweep_rows(runs: list[dict]) -> list[dict]:
    """One row per (policy, crews), in first-seen order: weighted risk-hours median, 5th and 95th percentile over seeds,
    and the median count of patients whose device ran out of backup in a dark home, out of `patients`."""
    groups: dict[tuple, list[dict]] = {}
    for r in runs:
        groups.setdefault((r["policy"], r["crews"]), []).append(r)
    return [{"policy": pol, "crews": crews, "median": float(np.median(w := [r["risk_hours_weighted"] for r in g])),
             "p5": float(np.percentile(w, 5)), "p95": float(np.percentile(w, 95)),
             "unweighted_median": float(np.median([r["risk_hours_unweighted"] for r in g])),
             "ran_out_median": float(np.median([r["patients_reaching_zero"] for r in g])), "patients": g[0]["patients"]}
            for (pol, crews), g in groups.items()]
