"""Hourly outdoor temperature and humidity (Iowa Mesonet ASOS, routine METARs) over the scenario window, UTC."""
import pandas as pd

from hearth.scenario import load, processed


def hourly_weather(scenario: str) -> pd.DataFrame:
    """Columns temp_c, rh on an hourly UTC index; each METAR goes to its nearest hour, gaps interpolated."""
    sc = load(scenario)
    if "weather_from" in sc:
        return hourly_weather(sc["weather_from"])
    grid = pd.date_range(sc["start"], sc["end"], freq="1h")
    if "weather" in sc:  # synthetic scenarios: constant {temp_c, rh}
        return pd.DataFrame({"temp_c": float(sc["weather"]["temp_c"]), "rh": float(sc["weather"]["rh"])}, index=grid)
    d = pd.read_csv(processed(f"weather_{scenario}.csv"), na_values="M")
    t = pd.to_datetime(d.valid, utc=True).dt.round("1h")
    w = pd.DataFrame({"temp_c": (d.tmpf.values - 32) * 5 / 9, "rh": d.relh.values}, index=t).groupby(level=0).mean()
    return w.reindex(grid).interpolate(limit_direction="both")
