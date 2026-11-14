import pytest

from hearth.messaging import guard, interpreter
from hearth.messaging.interpreter import interpret_turn

ctx = {"device": "oxygen", "profile_backup_hours": 6}
GOOD = '{"safe": null, "needs_help_now": null, "device_running": null, "backup_hours": 0.67, "can_move": null, "destination_offered": null, "consents_to_move": null, "confirms": null, "wants_human": false, "medical_question": false, "language": "en", "confidence": 0.9, "ack": null}'


def test_keypad_one_means_safe():
    t = interpret_turn("", "1", ctx, [])
    assert t.safe is True and t.confidence == 1.0


def test_bare_digit_reply_means_the_keypad_choice(monkeypatch):
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: pytest.fail("a keypad digit must not reach the model"))
    assert interpret_turn(" 1 ", None, ctx, []).safe is True


@pytest.mark.parametrize("text,yes", [("No.", False), ("yes", True), ("Yeah", True), ("that's right", True), ("nope", False)])
def test_plain_yes_or_no_is_read_by_code(monkeypatch, text, yes):
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: pytest.fail("a plain yes/no must not reach the model"))
    t = interpret_turn(text, None, ctx, [])
    assert t.confirms is yes and not t.wants_human and t.confidence == 1.0


def test_keypad_two_means_help_now():
    t = interpret_turn("", "2", ctx, [])
    assert t.needs_help_now is True and t.safe is None


def test_empty_turn_changes_nothing(monkeypatch):
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: pytest.fail("silence must not reach the model"))
    t = interpret_turn("", None, ctx, [])
    assert t.backup_hours is None and t.safe is None


def test_model_output_becomes_a_turn(monkeypatch):
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: GOOD)
    assert interpret_turn("about forty minutes", None, ctx, []).backup_hours == 0.67


def test_invalid_model_output_escalates_after_one_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: calls.append(a) or "not json")
    t = interpret_turn("uh", None, ctx, [])
    assert t.wants_human and t.confidence == 0 and t.backup_hours is None and len(calls) == 2


def test_retry_recovers_from_one_bad_output(monkeypatch):
    outs = iter(["not json", GOOD])
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: next(outs))
    assert interpret_turn("forty minutes", None, ctx, []).backup_hours == 0.67


def test_model_error_escalates(monkeypatch):
    def boom(*a): raise TimeoutError("model timed out")
    monkeypatch.setattr(interpreter, "_call_model", boom)
    t = interpret_turn("forty minutes", None, ctx, [])
    assert t.wants_human and t.confidence == 0


@pytest.mark.parametrize("line", [
    "Help is on the way.", "A driver will be there in 20 minutes.", "Someone's coming to you soon.",
    "You're safe now.", "Your tank was delivered.", "Don't worry, we'll send a car.", "Turn your oxygen down to 2 liters.",
    "They're almost there.", "We've got you covered.", "Assistance has been arranged.", "Ya viene la ayuda.",
])
def test_guard_blocks_promises_safety_timing_and_advice(line):
    assert not guard.allows(line)


@pytest.mark.parametrize("line", ["I hear you.", "Thank you for telling me.", "I'm sorry, that sounds hard.", "Okay, got it."])
def test_guard_allows_plain_acknowledgments(line):
    assert guard.allows(line)


@pytest.mark.live
def test_live_minutes_become_hours():
    t = interpret_turn("about forty minutes", None, ctx, [{"role": "agent", "text": "About how many hours of backup do you have?"}])
    assert t.backup_hours == pytest.approx(0.67, abs=0.05) and not t.wants_human


def test_eval_scoring_counts_hours_within_ten_percent_and_escalations():
    from evals.run_interpreter import score
    rows = [
        ({"expected": {"backup_hours": 0.67}, "must_escalate": False}, interpreter.Turn(backup_hours=0.7, confidence=0.9)),
        ({"expected": {"backup_hours": 6}, "must_escalate": True}, interpreter.Turn(backup_hours=4, confidence=0.9)),
        ({"expected": {"needs_help_now": True}, "must_escalate": True}, interpreter.Turn(needs_help_now=True, confidence=0.9)),
    ]
    s = score(rows)
    assert s["backup_hours"] == (1, 2) and s["needs_help_now"] == (1, 1)
    assert s["escalation_tp"] == 1 and s["escalation_fn"] == 1 and s["escalation_fp"] == 0


@pytest.mark.live
def test_live_plain_no_to_a_readback_is_clear():
    hist = [{"role": "agent", "text": "About how many hours of backup do you have?"}, {"role": "caller", "text": "more like forty minutes"},
            {"role": "agent", "text": "I have you at forty minutes of backup. Is that right?"}]
    for _ in range(2):
        t = interpret_turn("no", None, ctx, hist)
        assert t.confirms is False and not t.wants_human and t.confidence >= 0.7



@pytest.mark.parametrize("hours", ["-1", "12000"])
def test_out_of_range_hours_count_as_invalid_output(monkeypatch, hours):
    monkeypatch.setattr(interpreter, "_call_model", lambda *a: GOOD.replace('"backup_hours": 0.67', f'"backup_hours": {hours}'))
    t = interpret_turn("forty minutes", None, ctx, [])
    assert t.wants_human and t.backup_hours is None


def test_keypad_1_sets_no_intent():
    assert interpret_turn("", "1", ctx, []).intent is None


def test_the_eval_grades_the_new_fields():
    from evals.run_interpreter import score
    from hearth.messaging.interpreter import Turn
    case = lambda exp: {"expected": exp, "must_escalate": False}  # noqa: E731
    s = score([(case({"floor": 3}), Turn(floor=3, confidence=0.9)), (case({"door": "the side door"}), Turn(door="The side door by the pool", confidence=0.9)),
               (case({"intent": "safe"}), Turn(intent="help", confidence=0.9))])
    assert s["other"] == (2, 3)
