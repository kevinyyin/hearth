from pathlib import Path

import pytest
from pydantic import ValidationError

from hearth.config import a, assumptions
from hearth.contracts import Event, Patient, Snapshot, Sourced, run_id

SAMPLE = Path("results/sample__p3__c20__s1")
sample_patient = dict(
    patient_id="p1", lat=29.76, lon=-95.37, zip="77002", floor=3, device="oxygen",
    device_detail="concentrator", backup_hours_on_hand=6.0, use_rate=1.0, mobility="walks",
    can_self_relocate=True, temp_sensitive="heat", risk_weight=3.0, supplier_id="s1",
    building_id=None, phone_status="verified", profile_status="complete",
)


def walk_leaves(node):
    if isinstance(node, dict) and "value" in node:
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from walk_leaves(v)
    else:
        raise AssertionError(f"bare value without source: {node!r}")


def test_patient_is_always_synthetic():
    assert Patient(**sample_patient).synthetic is True
    with pytest.raises(ValidationError):
        Patient(**sample_patient | {"synthetic": False})


def test_sourced_rejects_unknown_source():
    with pytest.raises(ValidationError):
        Sourced(value=8, source="guess", confidence=0.5)


def test_run_id():
    assert run_id("beryl_2024", "p3", 20, 1) == "beryl_2024__p3__c20__s1"


def test_sample_files_match_contracts():
    for i in (0, 1):
        snap = Snapshot.model_validate_json((SAMPLE / f"snapshots/{i}.json").read_text())
        assert len(snap.patients) == 30
    lines = (SAMPLE / "events.jsonl").read_text().splitlines()
    assert len(lines) == 6
    for line in lines:
        Event.model_validate_json(line)


def test_every_assumption_has_source():
    leaves = list(walk_leaves(assumptions()))
    assert leaves
    for leaf in leaves:
        assert {"value", "source", "confirmed"} <= leaf.keys()


def test_a_reads_values():
    assert a("decision.margin_h") == 12 and a("risk_weight.ventilator") == 5


def test_responder_name_and_help_reason_bounds():
    from hearth.contracts import HelpRequest, Responder

    crew = dict(base_building_id="B", lat=29.7, lon=-95.4, vehicle="van")
    assert Responder(crew_id="Crew Alpha-1", **crew).on_duty and HelpRequest(patient_id="x").state == "waiting"
    for bad in (lambda: Responder(crew_id="a/b", **crew), lambda: Responder(crew_id="ok", **crew | {"vehicle": "bike"}),
                lambda: Responder(crew_id="ok", equipment=["laser"], **crew), lambda: HelpRequest(patient_id="x", reason="r" * 141)):
        with pytest.raises(ValidationError):
            bad()
