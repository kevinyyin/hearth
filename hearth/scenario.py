"""Scenario files (config/scenarios/<name>.yaml) and the data folders the simulation reads."""
from functools import cache

import yaml

from hearth.config import ROOT

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


@cache
def load(name: str) -> dict:
    return yaml.safe_load((ROOT / "config" / "scenarios" / f"{name}.yaml").read_text())


def processed(name: str):
    path = PROCESSED / name
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run: uv run python scripts/fetch_data.py")
    return path
