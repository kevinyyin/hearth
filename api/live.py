"""Live demo flow: what happens when a dispatcher approves a refuge proposal. Only the consent call, nothing else."""
from hearth.contracts import RefugeProposal


def start_call(patient_id: str, kind: str, proposal_id: str | None = None) -> str:
    from hearth.messaging.voice import start_call as voice_start_call  # lane V; imported late so the API runs without it

    return voice_start_call(patient_id, kind, proposal_id)


def dial(call_id: str) -> str | None:
    from hearth.messaging.voice import dial as voice_dial

    return voice_dial(call_id)


def on_approved(proposal: RefugeProposal) -> str:
    assert proposal.status == "approved"  # nothing contacts a patient about a move before approval
    return start_call(proposal.patient_id, "move_consent", proposal.proposal_id)
