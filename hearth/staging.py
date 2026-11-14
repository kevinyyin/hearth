"""Staging lots: where crews gather near an outage. A rule over CoStar's parking and lot fields proposes real lots; a
dispatcher picks one. CoStar says how big a lot is, not whether its owner agrees or it is clear, so a choice is a
lot to call about, never a booking."""
from hearth import dispatch, store
from hearth.buildings import tools
from hearth.config import a

NOT_STAGING = ("multifamily", "senior_housing")  # residents' own parking
KEYS = ("building_id", "name", "address", "zip", "property_type", "surface_spaces", "lot_acres")


def candidates(rows: list[dict], dark_zips: set[str], center: tuple[float, float], limit: int = 3) -> list[dict]:
    """The nearest lots to `center` that are big enough, not residents' parking, and in a ZIP nobody has asked for help from."""
    ok = [r for r in rows if r.get("property_type") not in NOT_STAGING and (r.get("surface_spaces") or 0) >= a("staging.min_surface_spaces")
          and r.get("zip") and r["zip"] not in dark_zips]
    km = lambda r: tools._km(center, (r["lat"], r["lon"]))
    return [{k: r.get(k) for k in KEYS} | {"name": r.get("name") or r["address"], "km": round(km(r), 1)} for r in sorted(ok, key=km)[:limit]]


def _where(patient_ids) -> list[dispatch.Where]:
    return [dispatch.locate(*who) for i in patient_ids if (who := dispatch.person(i))]


def scene() -> tuple[tuple[float, float], set[str]] | None:
    """(centre, dark ZIPs): from the open help requests, else from registered homes with no ZIP dark; None with neither."""
    asking = _where(r.patient_id for r in dispatch.requests() if r.state in dispatch.LIVE)
    at = asking or _where(h["patient_id"] for h in store.all("home") if "patient_id" in h)
    if not at:
        return None
    return (sum(w.lat for w in at) / len(at), sum(w.lon for w in at) / len(at)), {w.zip for w in asking}


def options() -> list[dict]:
    now = scene()
    return candidates(tools.costar_all(), now[1], now[0]) if now else []


def choose(building_id: str) -> dict:
    option = next((o for o in options() if o["building_id"] == building_id), None)
    if option is None:
        raise ValueError("not a current staging option")
    store.put("staging", "current", option)
    return option


def chosen() -> dict | None:
    """The dispatcher's lot, `stale` once someone in its ZIP has asked for help."""
    doc, now = store.get("staging", "current"), scene()
    return doc and doc | {"stale": bool(now) and doc.get("zip") in now[1]}


def clear() -> None:
    store.delete("staging", "current")
