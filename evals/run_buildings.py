"""python -m evals.run_buildings : the building agent against ten hand-labeled buildings.

Labels in evals/buildings_labels.csv: one row per building, a column per field. A value is the truth read by a
person from the raw layers; "unknown" means the layers do not show it; empty means not labeled. Reports per-field
accuracy, correct "unknown" answers, and silent fills (the agent gave a value where the layers show none; target 0).
"""
import csv
from collections import Counter, defaultdict

from hearth import store
from hearth.config import ROOT
from hearth.contracts import BuildingProfile

LABELS = ROOT / "evals" / "buildings_labels.csv"


def _same(truth: str, value) -> bool:
    t = truth.strip().lower()
    if isinstance(value, bool):
        return t in (("yes", "true") if value else ("no", "false"))
    try:
        return abs(float(t) - float(value)) <= 0.15 * max(1.0, abs(float(t)))  # widths and counts within 15%
    except (TypeError, ValueError):
        return t == str(value).strip().lower()


def score(profile: BuildingProfile, labels: dict[str, str]) -> dict[str, str]:
    out = {}
    for field, truth in labels.items():
        if not truth.strip() or field == "building_id":
            continue
        got = getattr(profile, field)
        filled = got.source != "default" and got.value is not None
        if truth.strip().lower() == "unknown":
            out[field] = "silent_fill" if filled else "right_unknown"
        else:
            out[field] = ("right" if _same(truth, got.value) else "wrong") if filled else "missed"
    return out


def main() -> None:
    per_field: dict[str, Counter] = defaultdict(Counter)
    rows = list(csv.DictReader(LABELS.open()))
    for row in rows:
        doc = store.get("profile", row["building_id"])
        if doc is None:
            print(f"{row['building_id']}: not surveyed yet (run python -m hearth.buildings sweep or open it in the map)")
            continue
        for field, verdict in score(BuildingProfile.model_validate(doc), row).items():
            per_field[field][verdict] += 1
    total = Counter()
    for field, c in sorted(per_field.items()):
        known = c["right"] + c["wrong"] + c["missed"]
        print(f"{field:20} accuracy {c['right']}/{known}  right unknown {c['right_unknown']}  silent fills {c['silent_fill']}")
        total += c
    print(f"silent fills overall: {total['silent_fill']} (target 0); labeled rows: {len(rows)}")


if __name__ == "__main__":
    main()
