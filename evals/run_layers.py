"""python -m evals.run_layers : one refuge decision under each added layer, for one wheelchair patient.

The refuge is the surveyed hotel CoStar 1508702 (CoStar has no elevator fields for any hotel; its scan showed an elevator in
lobby views). Each row adds one layer to the stored profile, with the fields of layers not yet added blanked, so nothing
is surveyed again; the last row adds the building office's answer by phone. Rows are reported as they come out. Writes
evals/layers.md (evals/report.md belongs to the interpreter eval, which rewrites it whole).
"""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from hearth import store
from hearth.buildings import status
from hearth.buildings.profile import FIELDS, UNKNOWN
from hearth.buildings.refuge import eligible
from hearth.config import ROOT, a
from hearth.contracts import BuildingProfile, Patient

REFUGE, PATIENT = "1508702", "demo-2"
LAYERS = [("CoStar", {"costar"}), ("+ aerial (Vexcel)", {"costar", "vexcel"}), ("+ scan (Matterport)", {"costar", "vexcel", "matterport"})]


def rows(profile: BuildingProfile, patient: Patient, office: str | None) -> list[tuple[str, bool, str]]:
    """(label, passes, first reason) for CoStar alone, then each layer added, then the building office's answer."""
    out = []
    for label, kept in LAYERS:
        p = profile.model_copy(update={f: UNKNOWN for f in FIELDS if getattr(profile, f).source not in kept | {"default"}})
        ok, why = eligible(p, patient)
        out.append((label, ok, why[0]))
    ok, why = eligible(profile, patient, elevator_confirmed=office)
    out.append(("+ building office call" if office else "+ building office call (no answer recorded)", ok, why[0]))
    return out


def _office(building_id: str) -> str | None:
    """The building office's answer, read without placing any call (a simulated one would write to the store)."""
    said = status.latest(building_id)
    if not (said and said["said_by"] == "building_office" and said.get("elevator") == "yes"
            and time.time() - said["t"] < a("refuge.building_answer_valid_h") * 3600):
        return None
    return f"the building's office said so by phone at {datetime.fromtimestamp(said['t'], ZoneInfo('America/Chicago')).strftime('%-I:%M %p')}"


def main() -> None:
    doc = store.get("profile", REFUGE)
    if doc is None:
        raise SystemExit(f"no stored profile for {REFUGE}: survey it first")
    rec = store.get("patient", PATIENT) or next(r for r in json.loads((ROOT / "data/demo/patients.json").read_text()) if r["patient_id"] == PATIENT)
    patient = Patient(**rec).model_copy(update={"mobility": "wheelchair_manual"})
    out = rows(BuildingProfile.model_validate(doc), patient, _office(REFUGE))
    report = "\n".join([
        "# Layer table", "",
        f"Refuge CoStar `{REFUGE}`, one simulated wheelchair patient, run {time.strftime('%Y-%m-%d %H:%M %Z')}. "
        "Each row adds a layer; fields from layers not yet added are blanked.", "",
        "| Layers | Passes the access check | First reason |", "|---|---|---|",
        *[f"| {label} | {'yes' if ok else 'no'} | {why} |" for label, ok, why in out], "",
        "No layer changed the result." if len({ok for _, ok, _ in out}) == 1 else "", ""])
    print(report)
    (ROOT / "evals" / "layers.md").write_text(report)


if __name__ == "__main__":
    main()
