import numpy as np
import pandas as pd

from hearth.outage import clean_curve, dark_mask, fraction_out
from hearth.weather import hourly_weather


def test_clean_curve_removes_single_interval_dropouts():
    s = pd.Series([900_000, 910_000, 2_500, 905_000, 900_000]); c = clean_curve(s, 1_827_686)
    assert c.iloc[2] * 1_827_686 > 800_000 and len(c.attrs["corrected"]) == 1  # returns a fraction (ledger ruling)


def test_fraction_never_exceeds_one():
    assert clean_curve(pd.Series([2_000_000.0] * 3), 1_827_686).max() <= 1.0


def test_fraction_out_is_clean_15_minute_utc():
    f = fraction_out("beryl_2024")
    assert str(f.index.tz) == "UTC" and (f.index.to_series().diff().dropna() == pd.Timedelta("15min")).all()
    assert f.between(0, 1).all() and f.max() > 0.3  # Beryl put well over a third of Harris County dark


def test_dark_mask_matches_curve_within_one_percent():
    r = np.random.default_rng(1).random(23_000); f = fraction_out("beryl_2024"); m = dark_mask(r, f)
    assert np.abs(m.mean(axis=1) - f.values).max() < 0.01


def test_hourly_weather_has_no_gaps():
    w = hourly_weather("beryl_2024")
    assert list(w.columns) == ["temp_c", "rh"] and not w.isna().any().any()
    assert (w.index.to_series().diff().dropna() == pd.Timedelta("1h")).all() and w.temp_c.between(15, 45).all()


def test_nobody_gets_power_back_for_one_interval():
    m = dark_mask(np.random.default_rng(1).random(23_000), fraction_out("beryl_2024"))
    assert not (m[:-2] & ~m[1:-1] & m[2:]).any()
