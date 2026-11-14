from hearth.contracts import PlanState

TEMPLATES: dict[str, str] = {
    "open_automated": "This is an automated call from Hearth for the {county} health department.",
    "impact_check": "The power is out at your address, and we're checking on your {device}. Our records say your backup should last about {hours}. Is that about right? You can answer, or press 1 for yes, 2 if you need help now, or 3 if it's different.",
    "ask_hours": "About how many hours of backup do you have?",
    "dialysis_check": "The power is out at your address. In how many hours is your next home dialysis treatment due? You can answer, or press 2 if you need help now.",
    "readback_hours": "I have you at {hours} of {supply}. Is that right?",
    "ask_temperature": "Is your home getting too hot or too cold?",
    "close_no_promise": "We'll call you again before your backup runs low. If you need help sooner, call this number back or call 911 in an emergency.",
    "move_offer": "Your home is forecast to become unsafe to stay in. The health department recommends moving you to {place}, which has power. Would you be willing to go?",
    "consent_readback": "I have that you agree to move to {place}. Is that right?",
    "move_confirmed_ride": "A driver from {org} has accepted your ride. They expect to arrive between {window}.",
    "delivery_confirmed": "{org} has accepted your delivery of {item}. They expect to arrive between {window}.",
    "medical_handoff": "I can't give medical advice. I'm passing your question to a person at the health department. If this is an emergency, call 911.",
    "human_handoff": "I've flagged this call for a person at the health department. If this is an emergency, hang up and call 911.",
    "scam_reassure": "I understand. We will never ask for payment, Social Security numbers, passwords or bank details. You can hang up and call the health department at {callback_number}.",
    "voicemail": "This is Hearth calling for the {county} health department. We will send you a text.",
    "text_fallback": "Hearth: Power is out at your address. Based on your profile, your {device} backup should last about {hours}. Reply 1 if you're OK, 2 if you need help now, or a number if your hours are different.",
    "call_summary": "Hearth: On our call you confirmed {facts}. Reply here or call this number if anything changes. In an emergency call 911.",
    # registration and check calls ({unit}, {walkup} and {parts} are pieces code builds from confirmed answers)
    "reg_open": "This is an automated call from Hearth for the {county} health department. Does someone at home use powered medical equipment, like oxygen, a ventilator, home dialysis or a feeding pump?",
    "reg_no_equipment": "If that changes, call this number. In an emergency, call 911.",
    "ask_device": "Which equipment is it: oxygen, a ventilator, home dialysis or a feeding pump?",
    "ask_address": "What's the street address, with the apartment number if there is one?",
    "readback_address": "I have {address}{unit}. Is that right?",
    "address_not_found": "I couldn't find that address.",
    "reg_ask_hours": "If the power went out, about how many hours would you be OK without your {device}?",
    "ask_unit": "What's your apartment number?",
    "ask_building": "Your complex has {n} buildings. Which building are you in?",
    "confirm_building": "That's in building {b}. Is that right?",
    "ask_floor_building": "Your building has {floors} floors{walkup}. Which floor are you on?",
    "ask_floor": "Which floor are you on?",
    "ask_elevator": "Is there an elevator in your building?",
    "ask_door_aerial": "Our aerial photo suggests parking on the {side} side of the building. Is the door a crew should use on that side?",
    "ask_door": "Which door should a crew use?",
    "ask_room": "Which room is the machine in?",
    "ask_room_beds": "Which room is the machine in: a bedroom, the living room, or somewhere else?",
    "readback_home": "I have you {parts}. Is that right?",
    "ask_which_part": "Which part is wrong?",
    "reg_close": "Thank you, you're registered. If a storm or outage reaches you, a call from this number is Hearth checking on you. If you need help, call this number and say help. In an emergency, call 911.",
    "check_open_storm": "A hurricane is forecast for your area. We're checking your details are still right.",
    "check_open": "Let's check your details.",
    "check_address": "We have you at {address}{unit}. Is that still right?",
    "check_hours": "We have you OK for about {hours} without your {device}. Is that still right?",
    "check_home": "We have you {parts}. Is that still right?",
    # a registered caller's menu and help by phone
    "menu": "If you need help now, say help, or press 2. If you're safe, say I'm safe. To check your details, say details.",
    "tracker_now": "Your request: {line}",
    "ask_walk": "Can you walk to a car, on your own or with someone helping?",
    "ask_wheelchair": "Do you use a wheelchair, or do you stay in bed?",
    "help_opened": "I've asked for a crew. We'll text you each step, and the arrival time once a crew accepts. If this is an emergency, hang up and call 911.",
    "help_already": "Your request is already in.",
    "safe_noted": "Thank you. I've noted that you're safe. Call this number if that changes.",
    "ask_elevator_working": "Is the elevator in your building working right now?",
    # a call to a building's office: never names a resident or says anyone there uses medical equipment
    "bldg_open": "This is an automated call from Hearth for the {county} health department, about {name} at {address}. Do you work at this building?",
    "bldg_not_staff": "Thank you. Sorry to bother you.",
    "bldg_power": "Does the building have power right now?",
    "bldg_elevator": "Is a passenger elevator running right now?",
    "bldg_readback": "I have that the building {power}{elevator}. Is that right?",
    "bldg_close": "Thank you. That's all we need.",
    # a text, not a call line
    "alert_text": "Simulated Harris County alert: a hurricane is forecast for your area. If you or someone at home relies on powered medical equipment, call Hearth at {line} so a crew knows how to reach you. In an emergency, call 911.",
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
