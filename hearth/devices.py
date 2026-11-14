"""Device backup clock."""
import numpy as np


def drain(backup_h, use_rate, dark, moved, dt_h) -> np.ndarray:
    return np.maximum(backup_h - use_rate * dt_h * (dark & ~moved), 0.0)
