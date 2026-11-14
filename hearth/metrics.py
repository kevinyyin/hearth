"""Hours at risk: device out of backup in a dark home, or home temperature unsafe, and not moved."""
import numpy as np


def at_risk(backup_h, dark, moved, temp_unsafe) -> np.ndarray:
    return (((backup_h <= 0) & dark) | temp_unsafe) & ~moved


def summarize(risk_matrix, weights, dt_h) -> dict:
    return {"risk_hours_unweighted": risk_matrix.sum() * dt_h, "risk_hours_weighted": (risk_matrix * weights).sum() * dt_h}
