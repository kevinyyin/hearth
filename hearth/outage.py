"""Fraction of the county's customers without power, from EAGLE-I, cleaned; and which patients are dark when."""
import numpy as np
import pandas as pd

from hearth.config import a
from hearth.scenario import load, processed


def clean_curve(customers_out: pd.Series, total_customers: int, window=None, onset=None) -> pd.Series:
    """Fraction out, 0..1. Inside `window` (start, end), or everywhere if None, a reading below dip_ratio times both
    sides' recent max is a glitch and is interpolated; readings from `onset` until the first real rise are ramped.
    attrs["corrected"] lists every replaced or clipped interval."""
    s = customers_out.astype(float)
    clipped = s > total_customers
    s = s.clip(upper=total_customers)
    w = int(a("outage.dip_window_h") * 4)  # shortcut: assumes 15-minute readings, as EAGLE-I gives
    before = s.shift(1).rolling(w, min_periods=1).max()
    after = s[::-1].shift(1).rolling(w, min_periods=1).max()[::-1]
    bad = s < a("outage.dip_ratio") * np.minimum(before, after)
    inside = pd.Series(True, index=s.index) if window is None else (s.index >= window[0]) & (s.index <= window[1])
    bad &= inside
    if onset is not None:
        risen = s.index[(s.index > onset) & (s >= a("outage.onset_fraction") * total_customers)]
        if len(risen):  # no real rise after onset: nothing to ramp
            bad |= (s.index > onset) & (s.index < risen[0])
    s[bad] = np.nan
    out = (s.interpolate(limit_direction="both") / total_customers).clip(0, 1)
    out.attrs["corrected"] = [str(i) for i in s.index[bad | clipped]]
    return out


def fraction_out(scenario: str) -> pd.Series:
    """UTC 15-minute index over the scenario window, values 0..1, cleaned; attrs["corrected"] lists fixed intervals."""
    sc = load(scenario)
    if "curve_from" in sc:
        return fraction_out(sc["curve_from"])
    grid = pd.date_range(sc["start"], sc["end"], freq="15min")
    if "curve" in sc:  # synthetic scenarios: [[hours from start, fraction], ...]
        hours, frac = zip(*sc["curve"])
        f = pd.Series(np.interp((grid - grid[0]) / pd.Timedelta("1h"), hours, frac), index=grid)
        f.attrs["corrected"] = []
        return f
    d = pd.read_csv(processed(f"eaglei_{scenario}.csv"), dtype={"fips_code": str})
    d = d[d.fips_code == sc["fips"]]
    raw = pd.Series(d.customers_out.values, index=pd.to_datetime(d.run_start_time, utc=True)).reindex(grid)
    onset = pd.Timestamp(sc["onset"])
    gaps = raw.isna() & (grid >= onset)  # EAGLE-I drops zero rows; a gap mid-outage is missing data, not restoration
    f = clean_curve(raw.fillna(0).mask(gaps), sc["customer_total"], window=(onset, grid[-1]), onset=onset)
    f.attrs["corrected"] = sorted(set(f.attrs["corrected"]) | {str(t) for t in grid[gaps]})
    return f


def dark_mask(r: np.ndarray, f: pd.Series) -> np.ndarray:
    """(ticks, patients): patient i is dark while r_i < f(t), so the lowest r lose power first and get it back last.
    A one-interval return between two dark intervals (a natural wiggle in the curve) stays dark."""
    m = r[None, :] < f.to_numpy()[:, None]
    m[1:-1] |= m[:-2] & m[2:]
    return m
