"""Data-layer tools for the building agent: CoStar, Vexcel, Matterport, and one vision call.

HEARTH_FIXTURES=1 reads hand-made fixtures from data/buildings/_fixtures/<id>/.
Real responses are cached as files under data/buildings/<id>/<layer>.json (git-ignored: sponsor data).
"""
import base64
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Callable

from hearth.config import ROOT, a, anthropic_headers

CACHE_ROOT = ROOT / "data" / "buildings"
FIXTURES = ROOT / "data" / "buildings" / "_fixtures"


def _fixtures_on() -> bool:
    return os.environ.get("HEARTH_FIXTURES") == "1"


def _safe(building_id: str) -> str:
    # building ids reach file paths from the API; refuse anything path-like
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", building_id):
        raise ValueError(f"bad building id: {building_id!r}")
    return building_id


def _fixture(building_id: str, layer: str) -> dict | None:
    path = FIXTURES / _safe(building_id) / f"{layer}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _km(p: tuple[float, float], q: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = map(lambda x: (math.radians(x[0]), math.radians(x[1])), (p, q))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def cached(building_id: str, layer: str, fetch: Callable[[], Any]) -> tuple[Any, bool]:
    """(value, was_cached). Never caches None, so a missing layer is retried next time."""
    path = CACHE_ROOT / _safe(building_id) / f"{layer}.json"
    if path.exists():
        return json.loads(path.read_text()), True
    value = fetch()
    if value is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    return value, False


def _real(name: str):
    raise NotImplementedError(f"real {name} client not written yet (Task 2 step 6); set HEARTH_FIXTURES=1")


def costar_record(building_id: str) -> dict | None:
    if _fixtures_on():
        return _fixture(building_id, "costar")
    return _real("costar")


def costar_search(property_types: list[str], center: tuple[float, float], radius_km: float, limit: int = 20) -> list[dict]:
    if not _fixtures_on():
        return _real("costar")
    rows = [json.loads(p.read_text()) for p in sorted(FIXTURES.glob("*/costar.json"))]
    rows = [r for r in rows if r["property_type"] in property_types and _km(center, (r["lat"], r["lon"])) <= radius_km]
    return sorted(rows, key=lambda r: _km(center, (r["lat"], r["lon"])))[:limit]


def vexcel_attributes(lat: float, lon: float) -> dict | None:
    if not _fixtures_on():
        return _real("vexcel")
    for p in sorted(FIXTURES.glob("*/costar.json")):  # fixture attributes belong to the building at that point
        r = json.loads(p.read_text())
        if _km((lat, lon), (r["lat"], r["lon"])) < 0.05:
            return _fixture(r["building_id"], "vexcel")
    return None


def vexcel_image(building_id: str, lat: float, lon: float) -> Path | None:
    if not _fixtures_on():
        return _real("vexcel")
    path = FIXTURES / _safe(building_id) / "vexcel.png"
    return path if path.exists() else None


def matterport_panoramas(building_id: str) -> list[dict]:
    """[{pano_id, label, path}], [] when the building has no scan. Fixtures add a text `reading`."""
    if not _fixtures_on():
        return _real("matterport")
    scan = _fixture(building_id, "matterport")
    return scan["panoramas"] if scan else []


def matterport_embed_url(building_id: str) -> str | None:
    if not _fixtures_on():
        return _real("matterport")
    scan = _fixture(building_id, "matterport")
    return scan.get("embed_url") if scan else None


def look(image: Path, question: str) -> str:
    """One Claude vision call on an image file. Not unit-tested (network)."""
    import anthropic

    media = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    client = anthropic.Anthropic(default_headers=anthropic_headers())
    msg = client.messages.create(
        model=a("models.vision"), max_tokens=400,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(image.read_bytes()).decode()}},
            {"type": "text", "text": question + " Answer in two sentences or fewer. Say 'cannot tell' if the image does not show it."},
        ]}],
    )
    return msg.content[0].text
