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

from hearth.config import DATA, ROOT, a, anthropic_headers

CACHE_ROOT = DATA / "buildings"  # writable; fixtures below stay in the read-only repo
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


def _floor_plan(m: dict) -> dict:
    return {"name": m.get("modelName"), "beds": m.get("numBeds"), "scan_ids": _matterport_ids(m.get("attachments") or [], []),
            "units": [{"number": str(u["unitNumber"]), "building": u.get("buildingName")} for u in m.get("units") or [] if u.get("unitNumber")]}


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
    surface = [p["totalSpaces"] for p in r.get("parking") or [] if p.get("parkingType") == 1 and p.get("totalSpaces")]
    per_acre = {1: 43560, 2: 1}.get(r.get("lotSizeMeasurementType"))  # 1 square feet, 2 acres; anything else is unknown
    return {
        "surface_spaces": sum(surface) if surface else None,
        "lot_acres": round(r["lotSize"] / per_acre, 2) if per_acre and r.get("lotSize") else None,
        "building_id": str(r["id"]), "name": r.get("buildingName"), "zip": str(pa.get("postcode") or "")[:5] or None,
        "address": f"{street}, {pa.get('city')}, {pa.get('state')} {str(pa.get('postcode') or '')[:5]}",
        "lat": pa.get("latitude"), "lon": pa.get("longitude"), "property_type": kind,
        "floors": r.get("numStoriesAboveGrade"),
        "units": apt.get("totalNumUnits") or (r.get("propertyHospitality") or {}).get("numUnits"),
        "year_built": next((e.get("year") for e in r.get("constructionEvents") or [] if e.get("eventType") == 2), None),
        "construction": _MATERIAL.get(r.get("buildingConstructionMaterial")),
        "elevator_count": elevator_count, "elevator_note": elevator_note,
        # a hotel CoStar lists as temporarily (2) or permanently (3) closed is not a refuge
        "existing": r.get("constructionStatus") == 1 and (r.get("propertyHospitality") or {}).get("operatingStatus") not in (2, 3),
        "num_buildings": apt.get("numBuildings"), "walkup": apt.get("isWalkup"),
        "floor_plans": [plan for m in apt.get("models") or [] if (plan := _floor_plan(m))["units"] or plan["scan_ids"]],
        # building-level tours first, then model-unit tours
        "matterport_model_ids": _matterport_ids(r, _matterport_ids(r.get("attachments") or [], [])),
    }


_costar = None


def _costar_index() -> dict[str, dict]:
    """Houston records, normalized once and kept under data/buildings/_costar/ (git-ignored)."""
    global _costar
    if _costar is None:
        path = CACHE_ROOT / "_costar" / "houston_v4.json"  # bump the name when normalize_costar changes
        if not path.exists() and not COSTAR_FILE.exists():  # a host without the kit reads the index from storage
            from hearth import remote

            # the previous index has no lot fields (so no staging lots) but keeps every building route answering
            # on a host where the new file is not uploaded yet
            path = remote.fetch("costar/houston_v4.json") or remote.fetch("costar/houston_v3.json") or path
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


def costar_all() -> list[dict]:
    """Every building we can survey: the fixtures, or the Houston CoStar records still standing."""
    if _fixtures_on():
        return [json.loads(p.read_text()) for p in sorted(FIXTURES.glob("*/costar.json"))]
    return [r for r in _costar_index().values() if r["existing"]]


def costar_search(property_types: list[str], center: tuple[float, float], radius_km: float, limit: int = 20) -> list[dict]:
    rows = [r for r in costar_all() if r["property_type"] in property_types and _km(center, (r["lat"], r["lon"])) <= radius_km]
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
        "stories_below_eave": s.get("roof-characteristics.number-of-stories-below-eave"),
        "max_roof_height_m": s.get("roof-characteristics.maximum-roof-height"),
        "entrance_elevation_m": s.get("roof-characteristics.entrance-elevation"), "ac_units": s.get("roof-objects.ac-unit.count"),
    }


DETECT_LABELS = ("building entrance", "loading zone", "parking space", "driveway", "ramp")
_SIDES = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")


def summarize_detections(j: dict, lat: float, lon: float) -> list[dict]:
    """elements/detect -> [{label, confidence, side, distance_m}], best first: where each found thing sits from the point."""
    rows = []
    for f in j.get("features") or []:
        for d in f["properties"].get("detections") or []:
            pts = [tuple(map(float, xy.split())) for xy in re.findall(r"-?[\d.]+ -?[\d.]+", d.get("bbox") or "")]
            if not pts:
                continue
            ring = pts[:-1] if len(pts) > 1 and pts[0] == pts[-1] else pts  # a WKT ring repeats its first point
            clon, clat = sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring)
            dy, dx = (clat - lat) * 111_320, (clon - lon) * 111_320 * math.cos(math.radians(lat))
            side = _SIDES[round(math.degrees(math.atan2(dx, dy)) / 45) % 8]
            rows.append({"label": f["properties"]["label"], "confidence": round(d["confidence"], 2), "side": side,
                         "distance_m": round(math.hypot(dx, dy))})
    return sorted(rows, key=lambda r: -r["confidence"])


def vexcel_detect(lat: float, lon: float, labels: tuple[str, ...] = DETECT_LABELS) -> list[dict]:
    """Open-vocabulary detection (sam3) on the ortho around the point; where parking, driveways and entrances are."""
    if _fixtures_on():
        for p in sorted(FIXTURES.glob("*/costar.json")):
            r = json.loads(p.read_text())
            if _km((lat, lon), (r["lat"], r["lon"])) < 0.05:
                return (_fixture(r["building_id"], "vexcel") or {}).get("detections", [])
        return []
    pt = f"POINT({lon} {lat})"
    r = _vexcel("POST", "/elements/detect", json={
        "wkt": pt, "srid": 4326, "buffer-meter": 40,
        "images": [{"endpoint": "ortho/extract", "request": {"layer": VEXCEL_LAYERS, "srid": 4326, "wkt": pt, "buffer-meter": 40, "crop": "bounding_box"}}],
        "model-input": {"elements": [{"label": lab, "model": "sam3", "detection-threshold": 0.4} for lab in labels],
                        "include": ["bbox", "confidence"]}})
    r.raise_for_status()
    return summarize_detections(r.json(), lat, lon)[:12]


def _points(coords) -> list:
    """Every [lon, lat] in a GeoJSON coordinates array, however deeply it nests."""
    if not coords:
        return []
    return [coords] if isinstance(coords[0], (int, float)) else [p for c in coords for p in _points(c)]


def tile_centers(j: dict) -> list[dict]:
    """embedding/extract -> [{lat, lon, score}], best first: the centre of each matched tile (tiles are about 66 m wide)."""
    out = []
    for f in j.get("features") or []:
        if pts := _points((f.get("geometry") or {}).get("coordinates")):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            out.append({"lat": round((min(ys) + max(ys)) / 2, 5), "lon": round((min(xs) + max(xs)) / 2, 5), "score": round(f["properties"]["score"], 3)})
    return sorted(out, key=lambda t: -t["score"])


def vexcel_search(lat: float, lon: float, half_m: float, text: str, limit: int) -> list[dict]:
    """Semantic search over the aerial tiles in a square around the point: the tiles that look most like `text`."""
    if _fixtures_on():
        return []  # fixtures hold no aerial search
    dlat, dlon = half_m / 111_320, half_m / (111_320 * math.cos(math.radians(lat)))
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    r = _vexcel("POST", "/embedding/extract", json={
        "wkt": f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))", "srid": 4326, "search-text": text,
        "include": "score,geometry,collection", "total-records": limit, "page-size": limit})
    r.raise_for_status()
    return tile_centers(r.json())


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


def vexcel_image(building_id: str, lat: float, lon: float, buffer_m: int = 40, name: str = "vexcel") -> Path | None:
    """Top-down tile, twice `buffer_m` across (80 m for a building, 300 m for its lot), saved once to data/buildings/<id>/<name>.png."""
    if _fixtures_on():
        path = FIXTURES / _safe(building_id) / f"{name}.png"
        return path if path.exists() else None
    path = CACHE_ROOT / _safe(building_id) / f"{name}.png"
    if not path.exists():
        r = _vexcel("POST", "/ortho/extract", json={"wkt": f"POINT({lon} {lat})", "srid": 4326, "layer": VEXCEL_LAYERS, "buffer-meter": buffer_m,
                                                    "crop": "bounding_box", "image-format": "png", "destination-dimensions": "800,800"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return path


ENTRANCE_QUESTION = (
    "This top-down aerial image is 80 m across with north up, centred on one building. Where is that building's main "
    "entrance for a crew arriving by road? Look for a canopy, a drop-off loop, or a walkway from the street or the parking. "
    'Reply with JSON only: {"x": <0 to 1 from the left edge>, "y": <0 to 1 from the top edge>, "note": "<what is there, '
    'under 15 words>"}.')


def parse_entrance(answer: str) -> dict | None:
    """A vision answer -> {x, y, note}, x and y as fractions of the tile. None when it names no point on the tile."""
    m = re.search(r"\{.*\}", answer, re.S)
    try:
        j = json.loads(m.group()) if m else {}
        x, y = float(j["x"]), float(j["y"])
    except (ValueError, KeyError, TypeError):
        return None
    return {"x": x, "y": y, "note": str(j.get("note") or "")} if 0 <= x <= 1 and 0 <= y <= 1 else None


def aerial_entrance(building_id: str, lat: float, lon: float) -> dict | None:
    """Where the way in most likely is on the aerial tile: a vision model's reading, saved once. For a home whose resident
    has marked no entrance. Vexcel's detector is not asked: it rarely finds a door from straight above."""
    if _fixtures_on():
        return None

    def read():
        img = vexcel_image(building_id, lat, lon)
        return parse_entrance(look(img, ENTRANCE_QUESTION)) if img else None
    return cached(building_id, "entrance", read)[0]


LOT_QUESTION = (
    "This top-down aerial image is 300 m across with north up, centred on one commercial building. Where is its open "
    "surface parking, relative to the building, and from which side or street does a van drive in? One sentence, under 30 words.")


def lot_reading(building_id: str, lat: float, lon: float) -> dict | None:
    """A vision model's line on where a staging lot's open parking is and how a van gets in, saved once."""
    if _fixtures_on():
        return None

    def read():
        img = vexcel_image(building_id, lat, lon, 150, "lot")
        return {"note": look(img, LOT_QUESTION).strip()} if img else None
    return cached(building_id, "lot", read)[0]


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


_MP_ROOMS = """query($id: ID!) { model(id: $id) { name rooms { label tags dimensions(units: metric) { areaFloor width depth } } } }"""


def normalize_rooms(model: dict) -> dict:
    """One scan's unit type (the model name, e.g. "2BR, 2BA - 1,000SF") and its rooms with sizes; blank rooms dropped."""
    rooms = []
    for r in model.get("rooms") or []:
        name, dims = r.get("label") or ", ".join(r.get("tags") or []), r.get("dimensions") or {}
        if not name and not dims:
            continue
        w, d = dims.get("width"), dims.get("depth")
        rooms.append({"room": name or "unlabeled room",
                      "width_m": round(min(w, d), 1) if w and d else None, "length_m": round(max(w, d), 1) if w and d else None,
                      "area_m2": round(dims["areaFloor"], 1) if dims.get("areaFloor") else None})
    return {"unit_type": model.get("name"), "rooms": rooms}


def matterport_rooms(building_id: str, model_ids: list[str] | None = None) -> list[dict]:
    """[{unit_type, rooms: [{room, width_m, length_m, area_m2}]}] per scan; [] when the building has no scan.
    `model_ids` limits the fetch to those scans (a floor plan's own)."""
    if _fixtures_on():
        return (_fixture(building_id, "matterport") or {}).get("units", [])
    auth = (os.environ["MATTERPORT_API_KEY"], os.environ["MATTERPORT_API_TOKEN"])
    units = []
    ids = model_ids if model_ids is not None else (costar_record(building_id) or {}).get("matterport_model_ids", [])
    for mid in ids[:MP_MODELS_PER_BUILDING]:
        r = httpx.post(MATTERPORT_GRAPH, json={"query": _MP_ROOMS, "variables": {"id": mid}}, auth=auth, timeout=30)
        r.raise_for_status()
        if model := (r.json().get("data") or {}).get("model"):
            units.append(normalize_rooms(model))
    return units


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


def matterport_scan_ids(building_id: str) -> list[str]:
    """The building's real scan models. Fixture scans are hand-written readings with no model behind them."""
    if _fixtures_on():
        return []
    return (costar_record(building_id) or {}).get("matterport_model_ids") or []


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
    client = anthropic.Anthropic(default_headers=anthropic_headers(), timeout=30, max_retries=1)  # the survey has a 90 s budget
    msg = client.messages.create(
        model=a("models.vision"), max_tokens=2000, output_config={"effort": a("models.vision_effort")},
        messages=[{"role": "user", "content": [
            *[{"type": "image", "source": {"type": "base64", "media_type": media(p), "data": base64.b64encode(p.read_bytes()).decode()}}
              for p in images],
            {"type": "text", "text": question + " Answer in two sentences or fewer. Say 'cannot tell' if the image does not show it."},
        ]}],
    )
    return " ".join(b.text for b in msg.content if b.type == "text").strip()  # skip thinking blocks
