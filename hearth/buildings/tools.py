"""Data-layer tools for the building agent: CoStar, Vexcel, Matterport, and one vision call.

HEARTH_FIXTURES=1 reads hand-made fixtures from data/buildings/_fixtures/<id>/.
Real responses are cached as files under data/buildings/<id>/<layer>.json (git-ignored: sponsor data).
"""
import base64
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from hearth.config import ROOT, a, anthropic_headers

CACHE_ROOT = ROOT / "data" / "buildings"
FIXTURES = ROOT / "data" / "buildings" / "_fixtures"
COSTAR_FILE = ROOT / "data/raw/costar/costar-hackathon-kit/data/commercial-property.jsonl"
VEXCEL_API = "https://api.vexcelgroup.com/v2"
VEXCEL_LAYERS = "urban,urban-r,wide-area,urban-g"  # the API picks the best available
MATTERPORT_GRAPH = "https://api.matterport.com/api/models/graph"


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


# ---- CoStar: a local data extract (commercial-property.jsonl), not an API ----
_TYPES = {5: "office", 2: "industrial", 6: "retail", 7: "flex", 3: "land", 10: "specialty", 13: "healthcare"}
_SENIOR_SUBTYPES = {26, 27, 28, 31, 142}  # assisted living, congregate senior, CCRC, skilled nursing, independent living
_MATERIAL = {1: "masonry", 2: "metal", 3: "concrete", 4: "steel", 5: "wood", 6: "masonry", 7: "masonry"}
_MATTERPORT_REF = {36, 234}


def _matterport_ids(node, out: list) -> list:
    if isinstance(node, dict):
        if node.get("videoExternalReferenceType") in _MATTERPORT_REF and node.get("videoKey") and node["videoKey"] not in out:
            out.append(node["videoKey"])
        for v in node.values():
            _matterport_ids(v, out)
    elif isinstance(node, list):
        for v in node:
            _matterport_ids(v, out)
    return out


def _elevators(r: dict) -> tuple[int | None, str]:
    apt = r.get("propertyApartment") or {}
    entries = list(apt.get("elevators") or [])
    for block in ("propertyOffice", "propertyRetail", "propertyIndustrial", "propertyFlex"):
        entries += ((r.get(block) or {}).get("structural") or {}).get("elevators") or []
    passenger = [e for e in entries if e.get("elevatorType") == 1]
    yes = [e for e in passenger if e.get("elevatorState") == 1]
    if yes:
        counts = [e["numElevators"] for e in yes if e.get("numElevators")]
        return (sum(counts), "passenger elevators listed") if counts else (1, "at least one passenger elevator; count not listed")
    if passenger:
        return 0, "listed as no passenger elevator"
    if apt.get("isWalkup") is True:
        return 0, "listed as a walk-up"
    return None, "no elevator information"


def normalize_costar(r: dict) -> dict:
    """One CoStar commercial-property record -> the flat fields the agent reads. Missing stays None."""
    pa = r.get("primaryAddress") or {}
    apt = r.get("propertyApartment") or {}
    ptype = r.get("propertyType")
    if ptype == 1:
        kind = "hotel"
    elif ptype == 11:
        kind = "senior_housing" if apt.get("apartmentLifestyleType") == 2 else "multifamily"
    elif ptype == 13 and r.get("propertySubtype") in _SENIOR_SUBTYPES:
        kind = "senior_housing"
    else:
        kind = _TYPES.get(ptype, "other")
    street = " ".join(str(pa[k]) for k in ("streetNumber", "streetDirection", "streetName", "streetType", "streetSuffix") if pa.get(k))
    elevator_count, elevator_note = _elevators(r)
    return {
        "building_id": str(r["id"]), "address": f"{street}, {pa.get('city')}, {pa.get('state')} {str(pa.get('postcode') or '')[:5]}",
        "lat": pa.get("latitude"), "lon": pa.get("longitude"), "property_type": kind,
        "floors": r.get("numStoriesAboveGrade"),
        "units": apt.get("totalNumUnits") or (r.get("propertyHospitality") or {}).get("numUnits"),
        "year_built": next((e.get("year") for e in r.get("constructionEvents") or [] if e.get("eventType") == 2), None),
        "construction": _MATERIAL.get(r.get("buildingConstructionMaterial")),
        "elevator_count": elevator_count, "elevator_note": elevator_note,
        "existing": r.get("constructionStatus") == 1,
        # building-level tours first, then model-unit tours
        "matterport_model_ids": _matterport_ids(r, _matterport_ids(r.get("attachments") or [], [])),
    }


_costar = None


def _costar_index() -> dict[str, dict]:
    """Houston records, normalized once and kept under data/buildings/_costar/ (git-ignored)."""
    global _costar
    if _costar is None:
        path = CACHE_ROOT / "_costar" / "houston.json"
        if not path.exists():
            rows = {}
            with COSTAR_FILE.open() as f:
                for line in f:
                    r = json.loads(line)
                    if (r.get("primaryAddress") or {}).get("researchMarketId") == 14:  # Houston research market
                        n = normalize_costar(r)
                        rows[n["building_id"]] = n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows))
        _costar = json.loads(path.read_text())
    return _costar


def costar_record(building_id: str) -> dict | None:
    if _fixtures_on():
        return _fixture(building_id, "costar")
    return _costar_index().get(_safe(building_id))


def costar_search(property_types: list[str], center: tuple[float, float], radius_km: float, limit: int = 20) -> list[dict]:
    if _fixtures_on():
        rows = [json.loads(p.read_text()) for p in sorted(FIXTURES.glob("*/costar.json"))]
    else:
        rows = [r for r in _costar_index().values() if r["existing"]]
    rows = [r for r in rows if r["property_type"] in property_types and _km(center, (r["lat"], r["lon"])) <= radius_km]
    return sorted(rows, key=lambda r: _km(center, (r["lat"], r["lon"])))[:limit]


# ---- Vexcel: REST API, header X-API-KEY ----
def _vexcel(method: str, path: str, **kw) -> httpx.Response:
    headers = {"X-API-KEY": os.environ["VEXCEL_API_KEY"]}
    for wait in (1, 2, 4, 0):  # the docs ask for exponential backoff on 429
        r = httpx.request(method, VEXCEL_API + path, headers=headers, timeout=60, **kw)
        if r.status_code != 429 or not wait:
            return r
        time.sleep(wait)
    return r


def normalize_vexcel(j: dict) -> dict | None:
    """Latest capture of the parcel at the point -> roof and shade attributes."""
    feats = [f["properties"] for f in j.get("features") or []]
    if not feats:
        return None
    p = max(feats, key=lambda q: (bool(q.get("request-information.inside-parcel")), q.get("metadata.ortho-date-estimate") or ""))
    structs = p.get("structures") or [{}]
    s = next((x for x in structs if x.get("primary-structure")), structs[0])
    pct = lambda v: None if v is None else round(v / 100, 4)
    return {
        "collection": p.get("metadata.collection"), "capture_date": p.get("metadata.ortho-date-estimate"),
        "building_type": s.get("building-type.class"), "roof_material": s.get("roof-characteristics.material.class"),
        "roof_condition_1_to_5": s.get("roof-characteristics.condition"), "roof_shape": s.get("roof-characteristics.shape.value"),
        "tree_cover_fraction": pct(s.get("roof-characteristics.tree-cover.percent")),
        "parcel_tree_cover_fraction": pct(p.get("parcel-tree-cover.percent")),
        "footprint_area_m2": s.get("footprint.area"), "structure_count": p.get("structure.count"),
        "solar_panels": s.get("roof-objects.solar-panel-photovoltaic.count"),
    }


def vexcel_attributes(lat: float, lon: float) -> dict | None:
    if not _fixtures_on():
        r = _vexcel("GET", "/property/extract", params={"wkt": f"POINT({lon} {lat})", "srid": 4326, "layer": VEXCEL_LAYERS,
                                                        "latest": "true", "include": "precomputed", "unit-system": "metric"})
        if r.status_code == 404:  # no parcel at that point
            return None
        r.raise_for_status()
        return normalize_vexcel(r.json())
    for p in sorted(FIXTURES.glob("*/costar.json")):  # fixture attributes belong to the building at that point
        r = json.loads(p.read_text())
        if _km((lat, lon), (r["lat"], r["lon"])) < 0.05:
            return _fixture(r["building_id"], "vexcel")
    return None


def vexcel_image(building_id: str, lat: float, lon: float) -> Path | None:
    """Top-down tile, 80 m across, saved once to data/buildings/<id>/vexcel.png."""
    if _fixtures_on():
        path = FIXTURES / _safe(building_id) / "vexcel.png"
        return path if path.exists() else None
    path = CACHE_ROOT / _safe(building_id) / "vexcel.png"
    if not path.exists():
        r = _vexcel("POST", "/ortho/extract", json={"wkt": f"POINT({lon} {lat})", "srid": 4326, "layer": VEXCEL_LAYERS, "buffer-meter": 40,
                                                    "crop": "bounding_box", "image-format": "png", "destination-dimensions": "800,800"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return path


# ---- Matterport: Model API (GraphQL, HTTP Basic token id:secret); model ids come from CoStar ----
_MP_QUERY = """query($id: ID!) { model(id: $id) { name locations { id label floor { label } room { label tags }
  panos { skybox(resolution: "high") { children } } } } }"""
MP_MODELS_PER_BUILDING, MP_SWEEPS_PER_MODEL = 4, 6  # shortcut: first sweeps of the first models only; raise if entrances are missed


def normalize_matterport(model_id: str, model: dict) -> list[dict]:
    """Model API locations -> panoramas in sweep order. Skybox faces 1-4 are the horizontal views (0 ceiling, 5 floor)."""
    def order(loc):
        label = str(loc.get("label") or "")
        return (0, int(label)) if label.isdigit() else (1, 0)

    out = []
    for loc in sorted(model.get("locations") or [], key=order):
        faces = next((p["skybox"]["children"] for p in loc.get("panos") or [] if (p.get("skybox") or {}).get("children")), None)
        if not faces:
            continue
        room = loc.get("room") or {}
        place = room.get("label") or ", ".join(room.get("tags") or []) or "unlabeled room"
        floor = (loc.get("floor") or {}).get("label") or "floor unknown"
        out.append({"pano_id": f"{model_id}-{loc['id']}", "label": f"{model.get('name')}: {place}, {floor}, sweep {loc.get('label')}",
                    "path": None, "faces": faces[1:5]})
    return out


def matterport_panoramas(building_id: str) -> list[dict]:
    """[{pano_id, label, path}], [] when the building has no scan. Fixtures add a text `reading`; real ones add `faces`."""
    if _fixtures_on():
        scan = _fixture(building_id, "matterport")
        return scan["panoramas"] if scan else []
    rec = costar_record(building_id)
    auth = (os.environ["MATTERPORT_API_KEY"], os.environ["MATTERPORT_API_TOKEN"])
    panos = []
    for mid in (rec or {}).get("matterport_model_ids", [])[:MP_MODELS_PER_BUILDING]:
        r = httpx.post(MATTERPORT_GRAPH, json={"query": _MP_QUERY, "variables": {"id": mid}}, auth=auth, timeout=30)
        r.raise_for_status()
        model = (r.json().get("data") or {}).get("model")
        if model:
            panos += normalize_matterport(mid, model)[:MP_SWEEPS_PER_MODEL]
    return panos


def matterport_faces(building_id: str, pano: dict) -> list[Path]:
    """Download a panorama's four horizontal faces once to data/buildings/<id>/panos/."""
    paths = []
    for i, url in enumerate(pano["faces"]):
        path = CACHE_ROOT / _safe(building_id) / "panos" / f"{_safe(pano['pano_id'])}_{i}.jpg"
        if not path.exists():
            r = httpx.get(url, timeout=30)
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
        paths.append(path)
    return paths


def matterport_embed_url(building_id: str) -> str | None:
    if _fixtures_on():
        scan = _fixture(building_id, "matterport")
        return scan.get("embed_url") if scan else None
    ids = (costar_record(building_id) or {}).get("matterport_model_ids") or []
    return f"https://my.matterport.com/show/?m={ids[0]}&play=1&qs=1" if ids else None


def look(image: Path | list[Path], question: str) -> str:
    """One Claude vision call on one image file, or several views of one place. Not unit-tested (network)."""
    import anthropic

    images = image if isinstance(image, list) else [image]
    media = lambda p: "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    client = anthropic.Anthropic(default_headers=anthropic_headers())
    msg = client.messages.create(
        model=a("models.vision"), max_tokens=2000, output_config={"effort": a("models.vision_effort")},
        messages=[{"role": "user", "content": [
            *[{"type": "image", "source": {"type": "base64", "media_type": media(p), "data": base64.b64encode(p.read_bytes()).decode()}}
              for p in images],
            {"type": "text", "text": question + " Answer in two sentences or fewer. Say 'cannot tell' if the image does not show it."},
        ]}],
    )
    return " ".join(b.text for b in msg.content if b.type == "text").strip()  # skip thinking blocks
