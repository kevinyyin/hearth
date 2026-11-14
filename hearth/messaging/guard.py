"""Checks a model-written acknowledgment before it is spoken. Only these exact lines pass; anything else is dropped."""
ACKS = ("I hear you.", "Thank you.", "Thank you for telling me.", "I'm sorry, that sounds hard.", "Okay, got it.",
        "I understand.", "Thanks for your patience.", "Got it, thank you.", "I'm sorry to hear that.", "Okay.")
_ALLOWED = {a.lower().rstrip(".") for a in ACKS}


def allows(model_text: str) -> bool:
    """True only for a known plain acknowledgment: nothing about help, timing, safety, numbers or medical matters."""
    return model_text.strip().lower().rstrip(".") in _ALLOWED
