"""A caller's spoken address and apartment number, matched to one CoStar building and one of its floor plans."""
import re

from hearth.buildings import tools

_SHORT = {"street": "st", "avenue": "ave", "drive": "dr", "road": "rd", "boulevard": "blvd", "lane": "ln", "court": "ct",
          "parkway": "pkwy", "north": "n", "south": "s", "east": "e", "west": "w"}
_UNIT_WORDS = re.compile(r"\b(APARTMENT|APT|UNIT|NUMBER|NO)\b")


def _tokens(street: str) -> list[str]:
    return [_SHORT.get(w, w) for w in re.sub(r"[^a-z0-9 ]", " ", street.lower()).split()]


def match_address(house: str, street: str, zip: str | None = None) -> dict | None:
    """The one building with this house number whose street holds every word the caller said; None for none or several."""
    said = set(_tokens(street))
    hits = []
    for rec in tools.costar_all():
        number, _, rest = rec["address"].split(",")[0].partition(" ")
        if number == house.strip() and said and said <= set(_tokens(rest)) and (not zip or rec.get("zip") == zip):
            hits.append(rec)
    return hits[0] if len(hits) == 1 else None


def norm_unit(s: str) -> str:
    """"00-1410", "Apt 14-10" and "#1410" all read as "1410"."""
    return re.sub(r"[#\s.\-]", "", _UNIT_WORDS.sub("", s.upper())).lstrip("0")


def match_unit(rec: dict, said: str) -> dict | None:
    """The floor plan that lists this apartment number, with CoStar's own spelling of the number."""
    want = norm_unit(said)
    for plan in rec.get("floor_plans") or []:
        for u in plan["units"]:
            if want and norm_unit(u["number"]) == want:
                return {"unit": u["number"], "plan": plan["name"], "beds": plan["beds"], "scan_ids": plan["scan_ids"], "building": u["building"]}
    return None
