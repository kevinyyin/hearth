# Voice Registration and Help by Phone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A resident registers, describes their home, asks for help, says they are safe and hears what happens next, all by phone; the building's CoStar record decides what the call asks, and the answers move the dispatch queue and the refuge check.

**Architecture:** New scripted call kinds (`register`, `check`, `menu`, `building_check`) on the existing ElevenLabs custom-model endpoint: the interpreter reads each turn into fields, code picks templates. A small registry module turns a call's confirmed facts into the existing `patient`, `contact` and `home` documents, which the merged help loop (`hearth/dispatch.py`), responder card and dispatch page already read. Tracker lines go out as Photon texts after each help-state change.

**Tech Stack:** Python 3.11, FastAPI, pydantic, the JSON document store (`hearth/store.py`, SQLite locally, Postgres hosted), Claude Haiku interpreter, ElevenLabs + Photon, Next.js 15 + React 19 + Tailwind 4, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-11-14-voice-registration-design.md`

## Global Constraints

- Work on a branch named `voice-registration`, not on `main`.
- The model writes nothing the caller hears. Every spoken line is a key in `hearth/messaging/templates.py`; the interpreter only fills `Turn` fields. The survey's `van_dropoff` sentence is never read out.
- A number (house number, apartment number, floor, hours) counts only after the caller confirms its read-back.
- Keypad 1 never records safe. Only `Turn.intent == "safe"`, which the interpreter sets from words, does.
- No call or text says a crew is coming, or gives an arrival time, before the crew taps Accept.
- Only numbers in `HEARTH_DEMO_CALLERS` can register. Every phone number in the CoStar kit is fake (area code 555) and is never dialed.
- Environment only, never in the repo or a log: `HEARTH_DEMO_CALLERS` (comma-separated E.164), `HEARTH_ALERT_PHONES` (comma-separated E.164), `HEARTH_BUILDING_PHONES` (comma-separated `building_id=+1...`), `HEARTH_LINE_NUMBER` (the line's number as it should be read in the alert). All four are added to `HOSTED` in `tests/conftest.py`.
- `Patient` is unchanged. `synthetic` stays true; every page keeps its "Simulated" label.
- Every new number goes in `config/assumptions.yaml` with a `source` and `confirmed: false`.
- No new dependencies in `pyproject.toml` or `web/package.json`.
- Exact copy: the alert text, the scan caption and the close are quoted in the tasks that use them.
- Run Python tests with `uv run pytest`; web checks with `npm --prefix web run build` and `npm --prefix web test -- --run`.

## Review Focus

1. **A spoken apartment number against CoStar's format.** Calais Midtown stores units as `00-1410`; a caller says "fourteen ten" or "apartment 14-10". They must match (Task 2, `test_norm_unit`).
2. **A caller who hangs up mid-registration and calls again.** No registration exists, so they get the registration call again, and the first call stays under "Needs a person" (Task 6, `test_a_caller_who_hung_up_registers_again`).
3. **A help-loop change for a resident with no phone** (every synthetic demo patient). Nothing is sent and nothing fails (Task 9, `test_no_phone_sends_nothing`).
4. **Matterport is slow or down when the address is confirmed.** The room question falls back to the bedroom wording within the timeout (Task 5, `test_room_lookup_failure_falls_back_to_bedrooms`).
5. **The storm button with nothing configured.** No alert phones and no registrants: empty lists and no error (Task 10, `test_storm_with_nothing_configured`).

---

### Task 1: CoStar reader: buildings, walk-up, floor plans, closed hotels

**Files:**
- Modify: `hearth/buildings/tools.py` (`normalize_costar`, `_costar_index` cache name, `matterport_rooms`)
- Modify: `data/buildings/_fixtures/B-SAMPLE/costar.json`
- Test: `tests/buildings/test_tools.py`

**Interfaces:**
- Produces, on every record from `tools.costar_record` / `costar_all`: `num_buildings: int | None` (`propertyApartment.numBuildings`), `walkup: bool | None` (`propertyApartment.isWalkup`), `floor_plans: list[{"name": str, "beds": int | None, "scan_ids": list[str], "units": list[{"number": str, "building": str | None}]}]` from `propertyApartment.models[]` (`modelName`, `numBeds`, `units[].unitNumber`, `units[].buildingName`, scan ids from the model's `attachments` via `_matterport_ids`); plans with neither units nor scans are dropped.
- Produces: `existing` is false for a hotel whose `propertyHospitality.operatingStatus` is 2 or 3.
- Produces: `matterport_rooms(building_id: str, model_ids: list[str] | None = None) -> list[dict]`; `model_ids` limits the fetch to those scans.

- [ ] **Step 1: Write the failing tests**

```python
def test_normalize_reads_buildings_walkup_and_floor_plans():
    n = tools.normalize_costar(raw(propertyApartment={"numBuildings": 3, "isWalkup": False, "models": [
        {"modelName": "The Avondale", "numBeds": 1, "units": [{"unitNumber": "00-1410", "buildingName": None}],
         "attachments": [{"videoExternalReferenceType": 36, "videoKey": "vkx"}]},
        {"modelName": "Empty", "numBeds": 2, "units": [], "attachments": []}]}))
    assert (n["num_buildings"], n["walkup"]) == (3, False)
    assert n["floor_plans"] == [{"name": "The Avondale", "beds": 1, "scan_ids": ["vkx"], "units": [{"number": "00-1410", "building": None}]}]

@pytest.mark.parametrize("status,existing", [(1, True), (2, False), (3, False), (None, True)])
def test_a_closed_hotel_is_not_existing(status, existing):
    assert tools.normalize_costar(raw(propertyType=1, propertyHospitality={"operatingStatus": status}))["existing"] is existing
```

`raw(**over)` is a test helper returning a minimal record: `{"id": 1, "propertyType": 11, "constructionStatus": 1, "primaryAddress": {"streetNumber": "1", "streetName": "Main", "city": "Houston", "state": "TX", "postcode": "77002", "latitude": 29.7, "longitude": -95.3}} | over`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/buildings/test_tools.py -k "floor_plans or closed_hotel" -v`
Expected: FAIL with `KeyError: 'num_buildings'` and the closed-hotel cases failing.

- [ ] **Step 3: Implement the fields in `normalize_costar`; rename the cache file `houston_v2.json` to `houston_v3.json` in both the local path and the `remote.fetch` path; add the `model_ids` filter to `matterport_rooms`**

Add to the B-SAMPLE fixture: `"num_buildings": 2, "walkup": false, "floor_plans": [{"name": "1BR, 1BA - 700SF (fixture)", "beds": 1, "scan_ids": ["fixture-B-SAMPLE"], "units": [{"number": "00-0310", "building": "A"}, {"number": "410", "building": null}]}]`.

- [ ] **Step 4: Run the tests, then check the real index**

Run: `uv run pytest tests/buildings -q` → all pass.
Run: `uv run python -c "from hearth.buildings import tools; r = tools.costar_record('7768847'); print(r['num_buildings'], r['walkup'], len(r['floor_plans'])); print(sum(1 for x in tools._costar_index().values() if x['property_type'] == 'hotel' and not x['existing']))"`
Expected: `3 False 15`, then a number of at least `5`.

- [ ] **Step 5: Upload the new index for the hosted API** (only where `SUPABASE_URL` is set in `.env`)

Run: `uv run python -c "from hearth import remote; from hearth.buildings import tools; remote.upload(tools.CACHE_ROOT / '_costar' / 'houston_v3.json', 'costar/houston_v3.json')"`

- [ ] **Step 6: Commit**

```bash
git add hearth/buildings/tools.py data/buildings/_fixtures/B-SAMPLE/costar.json tests/buildings/test_tools.py
git commit -m "feat(costar): read building count, walk-up, floor plans with units; closed hotels are not refuges"
```

---

### Task 2: Address and apartment matching

**Files:**
- Create: `hearth/buildings/address.py`
- Test: `tests/buildings/test_address.py`

**Interfaces:**
- Produces: `match_address(house: str, street: str, zip: str | None = None) -> dict | None`: the one record from `tools.costar_all()` whose address starts with `house` and whose street matches; `None` for none or several. Street matching lowercases, drops punctuation, maps suffixes and directions (`street→st, avenue→ave, drive→dr, road→rd, boulevard→blvd, lane→ln, court→ct, parkway→pkwy, north→n, south→s, east→e, west→w`), and matches when the said tokens are a subset of the record's street tokens. A given ZIP must equal the record's.
- Produces: `norm_unit(s: str) -> str` and `match_unit(rec: dict, said: str) -> dict | None` returning `{"unit": str, "plan": str, "beds": int | None, "scan_ids": list[str], "building": str | None}` (`unit` is CoStar's own spelling).

- [ ] **Step 1: Write the failing tests** (fixtures on: `monkeypatch.setenv("HEARTH_FIXTURES", "1")`)

```python
def test_matches_a_spoken_address():
    assert match_address("1200", "Fixture Street")["building_id"] == "B-SAMPLE"
    assert match_address("1200", "fixture")["building_id"] == "B-SAMPLE"

def test_a_wrong_number_or_zip_matches_nothing():
    assert match_address("1201", "Fixture St") is None and match_address("1200", "Fixture St", "77003") is None

def test_several_matches_count_as_none(monkeypatch):
    two = [{"building_id": i, "address": "1200 Fixture St, Houston, TX 77002", "zip": "77002"} for i in "ab"]
    monkeypatch.setattr(tools, "costar_all", lambda: two)
    assert match_address("1200", "Fixture St") is None

@pytest.mark.parametrize("said,want", [("00-1410", "1410"), ("Apt 14-10", "1410"), ("#1410", "1410"), ("b12", "B12"), ("unit 0310", "310")])
def test_norm_unit(said, want):
    assert norm_unit(said) == want

def test_match_unit_finds_the_plan_and_building():
    rec = tools.costar_record("B-SAMPLE")
    assert match_unit(rec, "310") == {"unit": "00-0310", "plan": "1BR, 1BA - 700SF (fixture)", "beds": 1, "scan_ids": ["fixture-B-SAMPLE"], "building": "A"}
    assert match_unit(rec, "999") is None and match_unit({}, "1") is None
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/buildings/test_address.py -v` → FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the three functions in `hearth/buildings/address.py`**

`norm_unit`: uppercase; drop the words `APT`, `APARTMENT`, `UNIT`, `NUMBER`, `NO`; drop `#`, spaces, dashes and dots; strip leading zeros.

- [ ] **Step 4: Run the tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/buildings/address.py tests/buildings/test_address.py
git commit -m "feat(costar): match a spoken address and apartment number to a CoStar building and floor plan"
```

---

### Task 3: Shapes: the home record, interpreter fields, templates, config

**Files:**
- Modify: `hearth/contracts.py` (`Home`), `hearth/messaging/interpreter.py` (`Turn`, `SYSTEM`, `_SCHEMA`), `hearth/messaging/templates.py`, `config/assumptions.yaml`, `tests/conftest.py`, `evals/interpreter_cases.jsonl`
- Modify: `web/lib/types.ts` (`Home`), plus every web use of `home.size` that the build flags (`web/app/responder/page.tsx`, `web/app/resident/page.tsx`)
- Test: `tests/test_contracts.py`, `tests/messaging/test_templates.py`, `tests/messaging/test_interpreter.py`

**Interfaces:**
- Produces, on `Home`: `size: Literal["shoebox", "microwave", "carry_on", "mini_fridge", "custom"] | None = None`; new optional fields `source: Literal["web", "phone"] = "web"`, `unit: str | None` (≤20), `complex_building: str | None` (≤40), `door: str = ""` (≤200), `door_from_aerial: bool = False`, `room: str = ""` (≤120), `scan_room: str | None` (≤80), `has_elevator: bool | None = None`, `mobility_asked: bool = False`, `said_at: datetime | None = None`.
- Produces, on `Turn` (all default `None`): `device: Literal["oxygen", "ventilator", "home_dialysis", "feeding_pump", "other"]`, `house_number: str`, `street: str`, `unit: str`, `zip: str`, `floor: int` (−5 to 200), `building: str`, `door: str`, `room: str`, `room_label: str`, `has_elevator: bool`, `elevator_working: Literal["yes", "no", "unknown"]`, `intent: Literal["help", "safe", "details"]`, `mobility: Literal["walks", "wheelchair", "bed"]`, `which_part: Literal["building", "floor", "door", "room"]`. `SYSTEM` gains one line per field; `room_label` must be copied verbatim from `patient_context.room_names` or be null; `intent: "safe"` only when the person says in words that they are safe.
- Produces, in `config/assumptions.yaml`: `registration.defaults` = `{device_detail: "not asked", use_rate: 1.0, mobility: bedbound, temp_sensitive: both, risk_weight: 1.0, supplier_id: none, can_self_relocate: false}`; `storm.forecast_zips` (the Harris County ZIPs in the Beryl replay's patients file); `refuge.building_answer_valid_h: 6`; `voice.room_lookup_timeout_s: 3`.
- Produces, in `templates.py`, these keys (spec copy where quoted; the builder words the rest within the spec's rules): `reg_open` ("This is an automated call from Hearth for the {county} health department. Does someone at home use powered medical equipment, like oxygen, a ventilator, home dialysis or a feeding pump?"), `reg_no_equipment` ("If that changes, call this number. In an emergency, call 911."), `ask_device`, `ask_address` ("What's the street address, with the apartment number if there is one?"), `readback_address` ("I have {address}{unit}. Is that right?"), `address_not_found` ("I couldn't find that address."), `reg_ask_hours` ("If the power went out, about how many hours would you be OK without your {device}?"), `ask_unit` ("What's your apartment number?"), `ask_building` ("Your complex has {n} buildings. Which building are you in?"), `confirm_building` ("That's in building {b}. Is that right?"), `ask_floor_building` ("Your building has {floors} floors{walkup}. Which floor are you on?"), `ask_floor`, `ask_elevator` ("Is there an elevator in your building?"), `ask_door_aerial` ("Our aerial photo suggests parking on the {side} side of the building. Is the door a crew should use on that side?"), `ask_door` ("Which door should a crew use?"), `ask_room` ("Which room is the machine in?"), `ask_room_beds` ("Which room is the machine in: a bedroom, the living room, or somewhere else?"), `readback_home` ("I have you {parts}. Is that right?"), `ask_which_part` ("Which part is wrong?"), `reg_close` ("Thank you, you're registered. If a storm or outage reaches you, a call from this number is Hearth checking on you. If you need help, call this number and say help. In an emergency, call 911."), `menu` ("If you need help now, say help, or press 2. If you're safe, say I'm safe. To check your details, say details."), `tracker_now` ("Your request: {line}"), `ask_walk` ("Can you walk to a car, on your own or with someone helping?"), `ask_wheelchair` ("Do you use a wheelchair, or do you stay in bed?"), `help_opened` ("I've asked for a crew. We'll text you each step, and the arrival time once a crew accepts. If this is an emergency, hang up and call 911."), `help_already` ("Your request is already in."), `safe_noted` ("Thank you. I've noted that you're safe. Call this number if that changes."), `check_open_storm` ("A hurricane is forecast for your area. We're checking your details are still right."), `check_open` ("Let's check your details."), `check_address` ("We have you at {address}{unit}. Is that still right?"), `check_hours`, `check_home`, `ask_elevator_working` ("Is the elevator in your building working right now?"), `bldg_open` ("This is an automated call from Hearth for the {county} health department, about {name} at {address}. Do you work at this building?"), `bldg_not_staff`, `bldg_power` ("Does the building have power right now?"), `bldg_elevator` ("Is a passenger elevator running right now?"), `bldg_readback`, `bldg_close` ("Thank you. That's all we need."), `alert_text` ("Simulated Harris County alert: a hurricane is forecast for your area. If you or someone at home relies on powered medical equipment, call Hearth at {line} so a crew knows how to reach you. In an emergency, call 911.").

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contracts.py
def test_a_home_from_a_call_needs_no_size():
    h = Home(patient_id="R-1", building_id="B-SAMPLE", ok_without_h=4, source="phone", unit="00-1410")
    assert h.size is None and h.source == "phone" and not h.mobility_asked

# tests/messaging/test_templates.py
NEW = ["reg_open", "ask_address", "readback_address", "reg_ask_hours", "ask_floor_building", "ask_door_aerial", "readback_home",
       "reg_close", "menu", "help_opened", "safe_noted", "check_address", "ask_elevator_working", "bldg_open", "alert_text"]
@pytest.mark.parametrize("key", NEW)
def test_new_keys_are_allowed_outside_moves(key):
    assert allowed(key, PlanState.OWN_BACKUP, "none")

def test_no_new_line_promises_a_crew():
    for key in NEW:
        assert not re.search(r"\b(on (its|the) way|will arrive|is coming)\b", TEMPLATES[key], re.I)

# tests/messaging/test_interpreter.py
def test_keypad_1_sets_no_intent():
    assert interpret_turn("", "1", {}, []).intent is None
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_contracts.py tests/messaging/test_templates.py tests/messaging/test_interpreter.py -q` → FAIL.

- [ ] **Step 3: Implement the shapes, templates and config; add the four environment names to `HOSTED`; make the web build pass with `size` nullable (the responder card shows "not asked")**

Add eight interpreter eval cases to `evals/interpreter_cases.jsonl`, one per new field family: an address with apartment ("1200 Fixture Street apartment 310" → house_number, street, unit), a floor ("the third floor" → 3), a door ("the side door by the pool"), a room with `room_names` in context ("in my bedroom" with `["Bedroom 1", "Kitchen"]` → room_label "Bedroom 1"), "I'm safe" → intent safe, "I need help" → intent help, "I walk with a walker" → mobility walks, "it's not working" after the elevator question → elevator_working no.

- [ ] **Step 4: Run all checks**

Run: `uv run pytest -q` → PASS. Run: `npm --prefix web run build` → compiles. Run: `npm --prefix web test -- --run` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/contracts.py hearth/messaging/interpreter.py hearth/messaging/templates.py config/assumptions.yaml tests evals/interpreter_cases.jsonl web
git commit -m "feat(voice): home record, interpreter fields, templates and assumptions for calls that register and help"
```

---

### Task 4: Registry: records from a call

**Files:**
- Create: `hearth/messaging/registry.py`
- Modify: `hearth/store.py` (add `delete`)
- Test: `tests/messaging/test_registry.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `Home` (Task 3), `a("registration.defaults")`, `tools.costar_record`.
- Produces: `store.delete(kind: str, id: str) -> None` (SQLite and Postgres).
- Produces: `demo_callers() -> set[str]`, `alert_phones() -> list[str]`, `building_phones() -> dict[str, str]` (environment parsing, spaces ignored).
- Produces: the facts contract between the call scripts and this module, keys in `call["facts"]`: `device`, `device_words`, `building_id`, `address`, `unit`, `plan`, `scan_id`, `complex_building`, `backup_hours`, `floor`, `has_elevator`, `door`, `door_from_aerial`, `room`, `scan_room`. The caller's number is `call["ctx"]["phone"]`.
- Produces: `save(call: dict) -> str | None`: once `device`, `building_id`, `backup_hours` and `floor` are all in the facts, writes (or updates) the `patient` (`R-` + 8 hex, defaults from config, lat/lon/ZIP from CoStar, `phone_status="unverified"`), the `contact` (`{"patient_id", "phone"}`) and the `home` (`source="phone"`, `ok_without_h=backup_hours`, `said_at=now`); sets `call["patient_id"]`; returns the patient id, else `None`.
- Produces: `patient_for_phone(phone: str) -> str | None` (newest phone home whose contact has that phone), `registrations() -> {"registered": [...], "needs_person": [...]}` (newest first; registered rows `{"patient", "home", "address", "call_id", "call_status"}`; needs-person rows are `register` calls with no `patient_id` that ended `handoff` or `escalated`: `{"call_id", "phone", "facts", "status", "started_at"}`), `reset(phone: str) -> int` (deletes `patient`, `contact`, `home` and `help` for each of that phone's registrations).

- [ ] **Step 1: Write the failing tests** (`HEARTH_DB` and `HEARTH_FIXTURES=1` per test, as in `tests/test_dispatch.py`)

```python
FULL = {"device": "oxygen", "device_words": "oxygen machine", "building_id": "B-SAMPLE", "address": "1200 Fixture St, Houston, TX 77002",
        "unit": "00-0310", "plan": "1BR, 1BA - 700SF (fixture)", "scan_id": "fixture-B-SAMPLE", "backup_hours": 4.0, "floor": 3}

def call(**facts): return {"call_id": "C-1", "kind": "register", "patient_id": None, "ctx": {"phone": "+15550001111"}, "facts": facts, "status": "active"}

def test_nothing_is_written_until_device_address_hours_and_floor():
    assert registry.save(call(**{k: v for k, v in FULL.items() if k != "floor"})) is None and store.all("patient") == []

def test_a_full_call_writes_patient_contact_and_home():
    pid = registry.save(c := call(**FULL))
    p, h = Patient(**store.get("patient", pid)), Home(**store.get("home", pid))
    assert pid.startswith("R-") and c["patient_id"] == pid and p.synthetic and p.mobility == "bedbound" and p.floor == 3
    assert store.get("contact", pid)["phone"] == "+15550001111"
    assert (h.source, h.ok_without_h, h.size, h.unit, h.scan_id) == ("phone", 4.0, None, "00-0310", "fixture-B-SAMPLE")

def test_saving_again_updates_the_same_records():
    c = call(**FULL); pid = registry.save(c); c["facts"]["door"] = "side door"
    assert registry.save(c) == pid and Home(**store.get("home", pid)).door == "side door" and len(store.all("patient")) == 1

def test_the_newest_registration_wins_for_a_phone():
    registry.save(call(**FULL)); second = registry.save(call(**FULL))
    assert registry.patient_for_phone("+15550001111") == second

def test_a_demo_patients_contact_is_not_a_registration():
    store.put("contact", "demo-2", {"patient_id": "demo-2", "phone": "+15550002222"})
    assert registry.patient_for_phone("+15550002222") is None

def test_reset_removes_a_phones_registrations():
    registry.save(call(**FULL))
    assert registry.reset("+15550001111") == 1 and registry.patient_for_phone("+15550001111") is None

def test_a_handed_off_register_call_needs_a_person():
    store.put("call", "C-9", call(device="oxygen") | {"call_id": "C-9", "status": "handoff", "started_at": 1.0})
    assert [r["call_id"] for r in registry.registrations()["needs_person"]] == ["C-9"]

def test_building_phones_parse(monkeypatch):
    monkeypatch.setenv("HEARTH_BUILDING_PHONES", "H-LEVEL=+15551230000, B-SAMPLE = +15551230001")
    assert registry.building_phones() == {"H-LEVEL": "+15551230000", "B-SAMPLE": "+15551230001"}
```

Add `test_delete_removes_a_document` to `tests/test_store.py`.

- [ ] **Step 2: Run them and see them fail** → `uv run pytest tests/messaging/test_registry.py tests/test_store.py -q`

- [ ] **Step 3: Implement `store.delete` and `hearth/messaging/registry.py`**

- [ ] **Step 4: Run the tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/store.py hearth/messaging/registry.py tests/messaging/test_registry.py tests/test_store.py
git commit -m "feat(voice): registry turns a call's confirmed facts into patient, contact and home records"
```

---

### Task 5: The registration and check scripts

**Files:**
- Create: `hearth/messaging/register.py`
- Modify: `hearth/messaging/scripts.py` (`opening` and `advance` hand kinds `register` and `check` to `register.py`)
- Test: `tests/messaging/test_register.py`

**Interfaces:**
- Consumes: `address.match_address`, `address.match_unit` (Task 2); `registry.save` (Task 4); `tools.costar_record`; `tools.matterport_rooms(building_id, model_ids)` (Task 1); `store.get("profile", building_id)["van_dropoff"]`; the `Turn` fields and template keys (Task 3).
- Produces: `opening(call: dict) -> Lines`, `advance(call: dict, t: Turn) -> Lines` for kinds `register` and `check`; `questions(rec: dict | None, facts: dict) -> list[str]` returning row ids in this order, each only when the spec's condition holds: `unit`, `building`, `floor`, `elevator`, `door`, `room`; `side(van_dropoff: str | None) -> str | None`.
- Produces: `call["ctx"]["room_names"]`, filled when the address is confirmed: the matched plan's scans, else the building's; the fetch runs in a thread joined for at most `voice.room_lookup_timeout_s`; on timeout or error, `[]`.

Rules the tests pin (all from the spec): equipment "no" ends the call (`done`) with `reg_no_equipment`; device `other` ends it with `human_handoff` (`handoff`); a second "no" to the address read-back, or no single match, gives `address_not_found` + `human_handoff` (`handoff`); a one-story record stores floor 1 and skips the floor question; `ask_floor_building` adds ", and no elevator" only when `walkup` is true; an unmatched apartment number is retried once, then kept as said; `room_label` counts only when it is in `room_names`; with no room names, `ask_room_beds`; the home read-back names only what was asked, and "no" asks `ask_which_part`, re-asks that one, and reads back again; `registry.save(call)` after every confirmed answer; `reg_close` ends the call `done`. A `check` call opens with `check_open_storm` (when `ctx["storm"]`) or `check_open`, and each step whose fact is known goes straight to its `check_*` read-back.

- [ ] **Step 1: Write the failing tests** (fake interpreter dict as in `tests/messaging/test_voice.py`; fixtures on; `start_call(None, "register", phone=...)` from Task 6 is not there yet, so build the call dict with a helper `new_call(kind="register", **ctx)` that mirrors the call document)

```python
def test_a_full_registration_writes_records_and_closes(): ...
    # turns: "yes" -> "oxygen" -> "1200 Fixture Street apartment 310" -> "yes" -> "4 hours" -> "yes"
    #        -> "yes" (to "That's in building A. Is that right?": B-SAMPLE has 2 buildings and unit 00-0310 is in A)
    #        -> "third floor" -> "the side door" -> "bedroom" -> "yes"
    # assert last line == render("reg_close"); registry.patient_for_phone(PHONE) is set; Home: unit "00-0310",
    # complex_building "A" (from the unit), door "the side door", source "phone"
def test_no_equipment_closes_and_stores_nothing(): ...
def test_another_device_hands_off(): ...
def test_an_address_not_found_hands_off_after_the_second_try(): ...
def test_a_correction_at_each_readback(): ...          # address no -> asked again; hours 4 -> "no, six" -> read back 6; home no -> "the floor" -> floor asked -> read back
def test_a_one_story_building_skips_the_floor(monkeypatch): ...   # record floors 1 -> facts floor 1, no ask_floor line
def test_questions_follow_the_record():
    plans = [{"name": "p", "beds": 1, "scan_ids": [], "units": [{"number": "1", "building": None}]}]
    assert questions({"floors": 8, "elevator_count": 1, "num_buildings": 2, "walkup": False, "floor_plans": plans}, {}) == ["unit", "building", "floor", "door", "room"]
    assert "elevator" in questions({"floors": 4, "elevator_count": None, "walkup": None}, {"floor": 3})
    assert "elevator" not in questions({"floors": 4, "elevator_count": 0, "walkup": True}, {"floor": 3})
    assert "floor" not in questions({"floors": 1}, {}) and "unit" not in questions({"floors": 8, "floor_plans": plans}, {"unit": "1"})
def test_side():
    assert side("likely in paved lot south of buildings") == "south" and side("by the front") is None and side(None) is None
def test_the_survey_sentence_is_never_spoken(monkeypatch): ...   # profile van_dropoff "likely in paved lot south of buildings": the line has "south side" and not "paved lot"
def test_a_room_label_must_be_a_room_name(): ...                 # room_label "Kitchen" not in names -> scan_room None, room words kept
def test_room_lookup_failure_falls_back_to_bedrooms(monkeypatch): ...  # matterport_rooms raises -> ctx room_names == [] and the room line is ask_room_beds
def test_a_check_call_reads_back_what_is_known(): ...            # registered facts -> first lines check_open_storm + check_address
```

Write each test body to the comment's turns and assertions.

- [ ] **Step 2: Run them and see them fail** → `uv run pytest tests/messaging/test_register.py -q`

- [ ] **Step 3: Implement `hearth/messaging/register.py` and the delegation in `scripts.py`**

`side`: the first of `north|south|east|west` (whole word, case-insensitive) in the text. `questions` reads the record fields from Task 1 and the facts from Task 4; it is the spec's table, row for row.

- [ ] **Step 4: Run the tests** → PASS. Run `uv run pytest tests/messaging -q` → the existing voice tests still pass.

- [ ] **Step 5: Commit**

```bash
git add hearth/messaging/register.py hearth/messaging/scripts.py tests/messaging/test_register.py
git commit -m "feat(voice): registration and check calls with questions chosen from the CoStar record"
```

---

### Task 6: Voice wiring: call kinds, inbound routing, dialing, reset

**Files:**
- Modify: `hearth/messaging/voice.py`, `hearth/messaging/photon.py` (`after_call`, `_facts_text`)
- Test: `tests/messaging/test_voice.py` (replace `test_an_inbound_call_from_a_number_a_person_entered_gets_one_impact_check`)

**Interfaces:**
- Consumes: `registry.patient_for_phone`, `registry.demo_callers`, `registry.building_phones`, `registry.reset` (Task 4).
- Produces: `start_call(patient_id: str | None, kind: Literal["impact", "move_consent", "register", "check", "menu", "building_check"], proposal_id: str | None = None, phone: str | None = None, building_id: str | None = None, storm: bool = False) -> str`. `register` and `menu` need `phone` (stored as `ctx["phone"]`); `building_check` needs `building_id` (`ctx["building_id"]`, `ctx["name"]`, `ctx["address"]`, `ctx["one_story"]`).
- Produces: `_inbound_call` routes a caller with a phone registration to `menu`, a caller on the demo list with none to `register`, and anyone else to `None` (the hand-off line). Contact documents no longer route inbound calls.
- Produces: `dial(call_id: str) -> str | None` dials `phone_of(patient_id)` for patient calls, `ctx["phone"]` for `register`/`menu`, and `registry.building_phones()[building_id]` for `building_check`; `None` when there is no number or no line.
- Produces: `after_call` does nothing when `call["patient_id"]` is `None`; `_facts_text` also lists a confirmed address and floor.
- Produces: `python -m hearth.messaging.voice reset <phone>` prints the number of registrations removed.

- [ ] **Step 1: Write the failing tests** (through `chat_completions` with a `TestClient`, system prompt `caller=<number> conversation=<id>`, as the replaced test does)

```python
def test_a_number_on_the_demo_list_gets_the_registration_call(monkeypatch): ...     # first line contains "powered medical equipment"
def test_a_registered_number_gets_the_menu(monkeypatch): ...                        # registry.save a full call for that phone; line ends with render("menu")
def test_a_demo_patients_contact_is_not_routed_to_an_impact_call(monkeypatch): ...  # contact p1 has the number, number not listed -> render("human_handoff")
def test_a_caller_who_hung_up_registers_again(monkeypatch): ...                     # first conversation ends after the address (three silences); a new conversation from the same number gets reg_open again, and registrations()["needs_person"] lists the first call
```

- [ ] **Step 2: Run them and see them fail** → `uv run pytest tests/messaging/test_voice.py -q`

- [ ] **Step 3: Implement the signature, routing, `dial`, `after_call` guard and the `reset` command**

- [ ] **Step 4: Run** `uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/messaging/voice.py hearth/messaging/photon.py tests/messaging/test_voice.py
git commit -m "feat(voice): demo callers register, registered callers get the menu, contacts no longer route inbound calls"
```

---

### Task 7: Registrants on the API and pages

**Files:**
- Modify: `api/main.py` (`_patient`, `GET /api/registrations`, `POST /api/calls`)
- Modify: `web/app/start/page.tsx`, `web/app/dispatch/page.tsx`, `web/app/responder/page.tsx`, `web/lib/types.ts`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `registry.registrations`, `registry.demo_callers` (Task 4); `voice.start_call` (Task 6).
- Produces: `_patient` returns a stored `patient` document before looking anywhere else.
- Produces: `GET /api/registrations` → the `registry.registrations()` shape.
- Produces: `POST /api/calls` with `CallIn(patient_id: str | None = None, kind: Literal["impact", "move_consent", "register"], phone: str | None = None)`; `register` answers 403 unless `phone` is in `demo_callers()`, else `{"call_id"}`.
- Produces, in `web/lib/types.ts`: `Registrations = { registered: { patient: Patient; home: Home; address: string; call_id: string | null; call_status: string | null }[]; needs_person: { call_id: string; phone: string; facts: Record<string, unknown>; status: string; started_at: number }[] }`.
- Pages: `/start` loses its Resident section. `/dispatch` polls `/api/registrations` and shows "Registered by phone" (address, unit, device, when) and, under "Needs a person", each needs-person call (number, what was confirmed). The responder `JobCard` shows, for `home.source === "phone"`, a "Said by phone" block with `said_at`: apartment and floor plan, building, floor, door, room, elevator; size reads "not asked"; the scan caption for a phone home is exactly "Scan of this resident's floor plan, matched from their apartment number. Not their own home."

- [ ] **Step 1: Write the failing API tests**

```python
def test_a_phone_registrant_is_found_by_the_patient_routes(client): ...   # store patient R-1 + home -> GET /api/patients/R-1/home is 200
def test_registrations_lists_phone_homes_and_calls_that_need_a_person(client): ...
def test_a_browser_register_call_needs_a_listed_phone(client, monkeypatch): ...  # 403 unlisted; listed -> 200 and call kind "register"
```

- [ ] **Step 2: Run them and see them fail** → `uv run pytest tests/test_api.py -q`

- [ ] **Step 3: Implement the routes and the three pages**

- [ ] **Step 4: Run** `uv run pytest -q` and `npm --prefix web run build` → PASS.

- [ ] **Step 5: Check in the browser** (`api` and `web` from `.claude/launch.json`): register one persona with `POST /api/calls` kind `register` and a few `/voice/v1/chat/completions` turns, or `registry.save` from a shell; then `/start` has no Resident section, `/dispatch` lists the registration, and after a help request `/responder`'s card shows "Said by phone". Screenshot each.

- [ ] **Step 6: Commit**

```bash
git add api/main.py web tests/test_api.py
git commit -m "feat: phone registrants on the API, the dispatch page and the crew's card; the resident link leaves /start"
```

---

### Task 8: Help by phone

**Files:**
- Modify: `hearth/messaging/register.py` (kind `menu`, the help branch), `hearth/messaging/scripts.py` (impact: `intent == "help"` goes to the help branch), `hearth/messaging/voice.py` (`_turn`: "needs help now"), `hearth/dispatch.py` (`tracker_lines`, `latest_line`)
- Test: `tests/messaging/test_help_by_phone.py`

**Interfaces:**
- Consumes: `dispatch.open_request`, `dispatch.mark_safe`, `dispatch.request`, `dispatch.tracker`.
- Produces: `dispatch.tracker_lines(r: HelpRequest | None) -> list[str]`: the done steps' text, with `{window}` filled as "2:10 PM and 2:25 PM" in `America/Chicago`; `dispatch.latest_line(patient_id: str) -> str | None`.
- Produces: `register.help_branch(call: dict) -> Lines`. Mobility not yet asked (`home.mobility_asked` false): `ask_walk`; yes → `walks_with_help`; no → `ask_wheelchair`; wheelchair → `wheelchair_power`; bed or unclear → `bedbound`; stored on the patient, `mobility_asked` set. Then `open_request`; `help_opened`, or on `ValueError` `help_already` + `tracker_now`. The call ends `done`.
- Produces: `menu` opens with `open_automated`, then `tracker_now` when a request is live, then `menu`. `intent` help → help branch; safe → `mark_safe` + `safe_noted` (on `ValueError`, `tracker_now`); details → the call becomes kind `check` and continues there. Keypad 2 counts as help (its `needs_help_now`); keypad 1 repeats the menu.
- Produces: on any call, "needs help now" opens the request at once with the mobility on record (no questions), keeps today's escalation flag, and says `help_opened` (plus `medical_handoff` first when it was a medical question).

- [ ] **Step 1: Write the failing tests** (dispatch fixture world as in `tests/test_dispatch.py`: `HEARTH_FIXTURES=1`, `_ask_model` patched, one car crew on duty; a registered `R-` patient from `registry.save`)

```python
def test_help_asks_how_they_move_then_opens_a_request(): ...      # menu -> "I need help" -> "yes" ; request state in (waiting, offered); mobility walks_with_help; line has "asked for a crew"
@pytest.mark.parametrize("answer,mobility", [("a wheelchair", "wheelchair_power"), ("I stay in bed", "bedbound"), ("hmm", "bedbound")])
def test_the_more_careful_mobility_is_recorded(answer, mobility): ...
def test_needs_help_now_opens_a_request_without_questions_and_flags_the_call(): ...
def test_a_live_request_is_already_in_and_read_back(): ...
def test_spoken_safe_marks_safe_but_keypad_1_does_not(): ...
def test_safe_while_riding_reads_the_latest_line(): ...
def test_an_impact_call_can_open_a_request(): ...
def test_the_menu_opens_with_the_latest_tracker_line(): ...
def test_tracker_lines_fill_the_window_in_houston_time(): ...      # accepted request -> line contains "between" and "PM" or "AM", not "{window}"
```

- [ ] **Step 2: Run them and see them fail** → `uv run pytest tests/messaging/test_help_by_phone.py -q`

- [ ] **Step 3: Implement the branch, the menu, the "needs help now" change and the two dispatch helpers**

- [ ] **Step 4: Run** `uv run pytest -q` → PASS (update the existing "needs help now" voice tests to the new lines).

- [ ] **Step 5: Commit**

```bash
git add hearth/messaging hearth/dispatch.py tests/messaging
git commit -m "feat(voice): ask for help, say safe, or check details by phone; the same queue as the resident page"
```

---

### Task 9: Tracker texts

**Files:**
- Modify: `hearth/messaging/photon.py` (`text_tracker`), `hearth/dispatch.py` (`_notify`)
- Test: `tests/messaging/test_photon.py`

**Interfaces:**
- Consumes: `dispatch.tracker_lines`, `dispatch.request` (Task 8); `phone_of`, `_send`.
- Produces: `photon.text_tracker(patient_id: str) -> list[str]`: sends each line of `tracker_lines` not yet sent for this request (keyed by the request's `times["waiting"]`) as "Hearth: {line}", in order; stores a `message` document per line `{"key": "tracker", "patient_id", "request_at", "body", "status"}`; returns the ids sent; no phone → `[]`; a failed send is stored as `failed`, logged, and does not raise.
- Produces: `dispatch._notify()` calls `text_tracker` for every request, after the lock is released, at the end of `open_request`, `mark_safe`, `crew_action`, `mark_handled`, `save_crew`, and `expire` when it released any offer. It imports `photon` inside the function (photon → voice → scripts → register → dispatch would be a cycle).

- [ ] **Step 1: Write the failing tests** (`photon._send` monkeypatched to append to a list; contact for `p4`)

```python
def test_each_tracker_line_is_texted_once(): ...   # open_request -> ["Hearth: Request received", "Hearth: A crew has been asked"]; dispatch.expire() -> nothing new; accept -> one new text containing "has accepted your ride" and "between"
def test_no_crew_or_time_is_texted_before_accept(): ...
def test_no_phone_sends_nothing(): ...             # demo patient without a contact: open_request sends nothing and does not raise
def test_a_failed_text_does_not_stop_the_help_loop(): ...   # _send raises -> crew_action("A", "accept") still returns state "accepted"
```

- [ ] **Step 2: Run them and see them fail** → `uv run pytest tests/messaging/test_photon.py -q`

- [ ] **Step 3: Implement `text_tracker` and `_notify`**

- [ ] **Step 4: Run** `uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/messaging/photon.py hearth/dispatch.py tests/messaging/test_photon.py
git commit -m "feat(voice): each new tracker line reaches a phone resident as one text"
```

---

### Task 10: Storm forecast button

**Files:**
- Modify: `hearth/messaging/registry.py` (`storm`), `api/main.py` (`POST /api/storm`), `web/app/dispatch/page.tsx`
- Test: `tests/messaging/test_registry.py`

**Interfaces:**
- Consumes: `registry.alert_phones`, `registrations`; `photon._send`; `voice.start_call(..., "check", storm=True)`, `voice.dial`; `a("storm.forecast_zips")`; `HEARTH_LINE_NUMBER`.
- Produces: `registry.storm() -> {"alerted": list[str], "dialed": list[str], "failed": list[str]}`: texts `render("alert_text", line=HEARTH_LINE_NUMBER)` to each alert phone; starts and dials a `check` call (storm) for each phone registration whose patient ZIP is in the forecast list; each failure is listed, not raised.
- Produces: `POST /api/storm` → `registry.storm()`. `/dispatch` gains a "Storm forecast (simulated)" button that shows the result.

- [ ] **Step 1: Write the failing tests**

```python
def test_storm_texts_alert_phones_and_calls_registrants_in_the_area(monkeypatch): ...   # one registrant in a forecast ZIP, one outside; sent == alert phones; dialed lists only the first
def test_storm_with_nothing_configured(): ...                                          # == {"alerted": [], "dialed": [], "failed": []}
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Implement `storm`, the route and the button**

- [ ] **Step 4: Run** `uv run pytest -q` and `npm --prefix web run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/messaging/registry.py api/main.py web/app/dispatch/page.tsx tests/messaging/test_registry.py
git commit -m "feat: simulated storm alert texts and check calls to phone registrants in the forecast area"
```

---

### Task 11: The live elevator question and the queue

**Files:**
- Create: `hearth/buildings/status.py`
- Modify: `hearth/messaging/scripts.py` (impact call), `hearth/dispatch.py` (`_rank`, `SYSTEM`)
- Test: `tests/messaging/test_voice.py`, `tests/test_dispatch.py`

**Interfaces:**
- Produces: `status.record(building_id: str, said_by: Literal["resident", "building_office"], call_id: str, power: bool | None = None, elevator: Literal["yes", "no", "unknown"] | None = None) -> None` (one `building_status` document per building, with the time) and `status.latest(building_id: str) -> dict | None`.
- Produces: the impact call asks `ask_elevator_working` after the hours read-back, only when the patient's floor is above 1 and the building has an elevator (`elevator_count` above 0 on record, or `home.has_elevator`); the answer goes to `status.record(..., "resident", ...)`.
- Produces: each `_rank` row gains `floor`, `elevator` (`{"state", "said_by"}` or `None`) and `minutes_at_building` (`profile.service_minutes(stored_profile, floor, working)`, `None` without a stored profile). `working` is the status's `elevator == "yes"` when a status exists, else `elevator_count` above 0. `SYSTEM` gains: "minutes_at_building is how long a crew needs inside the building to reach the person, longer when the elevator is out; weigh it against the hours left." The fallback key uses `hours − minutes_at_building / 60`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_impact_call_asks_about_the_elevator_above_floor_1(): ...   # p1 floor 6, B-SAMPLE elevator 1 -> after "yes" to the read-back, ask_elevator_working; "it's not working" -> status elevator "no", said_by resident
def test_no_elevator_question_on_floor_1(): ...
def test_rank_rows_carry_floor_elevator_and_minutes(monkeypatch): ...    # capture rows passed to _ask_model: minutes_at_building == 10 + 4 * floor with elevator "no"
def test_the_fallback_puts_a_stair_carry_first(monkeypatch): ...         # _ask_model raises; same hours; the floor-6 resident with the elevator out ranks above the floor-1 one
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Implement `status.py`, the impact step and the `_rank` change**

- [ ] **Step 4: Run** `uv run pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/buildings/status.py hearth/messaging/scripts.py hearth/dispatch.py tests
git commit -m "feat: a caller's elevator answer adds stair minutes and moves their request in the queue"
```

---

### Task 12: The building call

**Files:**
- Create: `hearth/messaging/building_call.py`
- Modify: `hearth/messaging/scripts.py` (delegate `building_check`), `hearth/buildings/refuge.py` (`confirm_elevator`, `eligible`, `access`), `api/main.py` (`POST /api/buildings/{id}/call`, building detail), `web/components/BuildingPanel.tsx`, `web/lib/types.ts`
- Test: `tests/messaging/test_building_call.py`, `tests/buildings/test_refuge.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `status.record`, `status.latest` (Task 11); `registry.building_phones` (Task 4); `voice.start_call(None, "building_check", building_id=...)`, `voice.dial` (Task 6).
- Produces: the script `bldg_open` → (no: `bldg_not_staff`, done, nothing recorded) → `bldg_power` → `bldg_elevator` (skipped for a one-story record) → `bldg_readback` → `bldg_close`; on a confirmed read-back, `status.record(building_id, "building_office", call_id, power=..., elevator=...)`.
- Produces: `confirm_elevator(building_id: str, dark_zips: set[str]) -> str | None`: a building-office status newer than `refuge.building_answer_valid_h` decides (`elevator == "yes"` → "the building's office said so by phone at {h:mm AM/PM}"; otherwise `None`); with none, today's simulated answer → "the refuge confirmed by phone that it is running (simulated call)" or `None`. `eligible(option_profile, patient, elevator_confirmed: str | None = None)` puts that phrase in its reasons. Update every caller (`refuge.access`, the two calls in `tests/buildings/test_refuge.py`).
- Produces: `POST /api/buildings/{id}/call` → `{"call_id", "conversation_id"}`, 403 when the building is not in `building_phones()`. `GET /api/buildings/{id}` adds `status` (`status.latest`) and `can_call`. The building panel shows the status with who said it and when, and a "Call the building" button when `can_call`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_office_answers_are_recorded(): ...           # yes, yes, yes, yes -> status power True, elevator "yes", said_by building_office
def test_someone_who_does_not_work_there_ends_the_call(): ...
def test_a_one_story_building_skips_the_elevator(): ...
def test_no_line_mentions_a_resident(): ...               # every spoken line: no "resident", "patient", "medical", "equipment", "oxygen"
def test_a_fresh_office_answer_decides(monkeypatch): ...  # office "no" -> None even outside the dark area; office "yes" -> phrase contains "office said so by phone"
def test_a_stale_office_answer_falls_back_to_the_simulated_call(monkeypatch): ...
def test_calling_an_unlisted_building_is_refused(client): ...   # 403
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Implement the script, the refuge change, the route and the panel**

- [ ] **Step 4: Run** `uv run pytest -q` and `npm --prefix web run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add hearth/messaging/building_call.py hearth/messaging/scripts.py hearth/buildings/refuge.py api/main.py web tests
git commit -m "feat: call a building's office about power and the elevator; a real answer replaces the simulated one"
```

---

### Task 13: The layer table

**Files:**
- Create: `evals/run_layers.py`
- Modify: `evals/report.md` (a section written by the script)
- Test: `tests/buildings/test_layers.py`

**Interfaces:**
- Consumes: `refuge.eligible` with `elevator_confirmed: str | None` (Task 12); `profile.UNKNOWN`, `profile.FIELDS`.
- Produces: `rows(profile: BuildingProfile, patient: Patient, office: str | None) -> list[tuple[str, bool, str]]`: labels `"CoStar"`, `"+ aerial (Vexcel)"`, `"+ scan (Matterport)"`, `"+ building office call"`; each row blanks to `UNKNOWN` every field whose source is a layer not yet added, and gives `(label, ok, first reason)`. `main()` loads the stored profile for `1508702`, a wheelchair patient (`demo-2`, mobility forced to `wheelchair_manual` if needed), the latest office status, and replaces the "Layer table" section of `evals/report.md`.

- [ ] **Step 1: Write the failing test** (fixture profile from `tests/buildings/bhelpers.profile`)

```python
def test_each_row_adds_one_layer():
    out = rows(profile("H-LEVEL", step_free=True, floors=5, elevators=2), WHEELCHAIR, office=None)
    assert [r[0] for r in out] == ["CoStar", "+ aerial (Vexcel)", "+ scan (Matterport)", "+ building office call"]
    assert all(isinstance(ok, bool) and reason for _, ok, reason in out)
```

- [ ] **Step 2: Run it and see it fail**

- [ ] **Step 3: Implement `rows` and `main`**

- [ ] **Step 4: Run** `uv run pytest tests/buildings/test_layers.py -q` → PASS. Run `uv run python -m evals.run_layers` → the report section exists with four rows, as they came out.

- [ ] **Step 5: Commit**

```bash
git add evals/run_layers.py evals/report.md tests/buildings/test_layers.py
git commit -m "eval: one refuge decision under each added layer, including the building office call"
```

---

### Task 14: Spec and demo readiness

**Files:**
- Modify: `docs/spec.md` (the new routes in its route table; the rules: demo callers only, kit numbers never dialed, keypad never records safe; the phone as the resident's way in; `/start` without the Resident link)

- [ ] **Step 1: Update `docs/spec.md`**

- [ ] **Step 2: Survey the demo building once** with the `api` server running: `curl -N http://localhost:8001/api/buildings/7768847/survey > /dev/null`, then `uv run python -c "from hearth import store; print(store.get('profile', '7768847')['van_dropoff'])"` → a value (or `None`: the door question will be plain; say so in the demo notes).

- [ ] **Step 3: Run the interpreter eval** `uv run python -m evals.run_interpreter` and check the new cases' rows in `evals/report.md`.

- [ ] **Step 4: Full check** `uv run pytest -q` and `npm --prefix web run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/spec.md evals/report.md
git commit -m "docs: spec for registration and help by phone"
```
