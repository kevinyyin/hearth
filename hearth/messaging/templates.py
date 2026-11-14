from hearth.contracts import PlanState

TEMPLATES: dict[str, str] = {
    "open_automated": "This is an automated call from Hearth for the {county} health department.",
    "impact_check": "The power is out at your address, and we're checking on your {device}. Our records say your backup should last about {hours}. Is that about right? You can answer, or press 1 for yes, 2 if you need help now, or 3 if it's different.",
    "ask_hours": "About how many hours of backup do you have?",
    "readback_hours": "I have you at {hours} of {supply}. Is that right?",
    "ask_temperature": "Is your home getting too hot or too cold?",
    "close_no_promise": "We'll call you again before your backup runs low. If you need help sooner, call this number back or call 911 in an emergency.",
    "move_offer": "Your home is forecast to become unsafe to stay in. The health department recommends moving you to {place}, which has power. Would you be willing to go?",
    "consent_readback": "I have that you agree to move to {place}. Is that right?",
    "move_confirmed_ride": "A driver from {org} has accepted your ride. They expect to arrive between {window}.",
    "delivery_confirmed": "{org} has accepted your delivery of {item}. They expect to arrive between {window}.",
    "medical_handoff": "I can't give medical advice. I'm passing your question to a person at the health department. If this is an emergency, call 911.",
    "human_handoff": "I'm connecting you with a person at the health department.",
    "scam_reassure": "I understand. We will never ask for payment, Social Security numbers, passwords or bank details. You can hang up and call the health department at {callback_number}.",
    "voicemail": "This is Hearth calling for the {county} health department. We will send you a text.",
    "text_fallback": "Hearth: Power is out at your address. Based on your profile, your {device} backup should last about {hours}. Reply 1 if you're OK, 2 if you need help now, or a number if your hours are different.",
    "call_summary": "Hearth: On our call you confirmed {facts}. Reply here or call this number if anything changes. In an emergency call 911.",
}
KEYS: tuple[str, ...] = tuple(TEMPLATES)
PROMISE_KEYS = {"move_confirmed_ride", "delivery_confirmed"}
_MOVE_ONLY = {"move_offer", "consent_readback"}


def render(key: str, **vars) -> str:
    return TEMPLATES[key].format(**vars)


ALLOWED: dict[tuple[PlanState, str], set[str]] = {
    (state, job): set(KEYS) - PROMISE_KEYS - (set() if state is PlanState.MOVE else _MOVE_ONLY)
    for state in PlanState
    for job in ("none", "created", "accepted", "completed", "failed")
}
ALLOWED[PlanState.MOVE, "accepted"].add("move_confirmed_ride")
ALLOWED[PlanState.RESUPPLY, "accepted"].add("delivery_confirmed")


def allowed(key: str, state: PlanState, job_status: str) -> bool:
    return key in ALLOWED.get((state, job_status), ())


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


# shortcut: covers 0 to 999 only (so backup under 1000 hours), extend if longer backups appear
def _words(n: int) -> str:
    if n >= 100:
        return _ONES[n // 100] + " hundred" + (" " + _words(n % 100) if n % 100 else "")
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10 - 2] + ("-" + _ONES[n % 10] if n % 10 else "")


def say_hours(hours: float) -> str:
    minutes = int(hours * 12 + 0.5) * 5  # nearest 5 minutes
    if minutes < 60:
        return f"{_words(minutes)} minutes"
    if minutes >= 480:
        return f"about {_words((minutes + 30) // 60)} hours"
    whole, quarters = divmod(round(minutes / 15), 4)
    part = ("", " and a quarter", " and a half", " and three quarters")[quarters]
    unit = "hour" if (whole, quarters) == (1, 0) else "hours"
    return f"{_words(whole)}{part} {unit}, that's {_words(minutes)} minutes"
