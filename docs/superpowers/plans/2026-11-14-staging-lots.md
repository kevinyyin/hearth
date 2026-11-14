# Staging Lots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The dispatch page proposes a real CoStar parking lot to stage crews at, with a Vexcel aerial of the lot, and the dispatcher approves it.

**Architecture:** Two new fields on the normalized CoStar record feed a pure ranking rule in a new `hearth/staging.py`. Three small API routes expose the options, the choice and the lot tile; a vision reading of the tile is fetched lazily per option, like the existing entrance reading. One new card on the dispatch page and one line on the crew page show it.

**Tech Stack:** Python 3 / FastAPI / pytest; Next.js / TypeScript; existing `hearth.store`, `hearth.dispatch`, `hearth.buildings.tools`.

**Spec:** `docs/superpowers/specs/2026-11-14-staging-lots-design.md`

## Global Constraints

- Work in a new worktree on a branch `staging-lots` cut from `main`. The spec and this plan are untracked in the `central-planner` checkout: copy both into the worktree and commit them with Task 1.
- Do not touch `hearth/sim/`, `hearth/planner.py`, `hearth/alns.py`, `planner.depots`, or anything under `results/`.
- No new agent and no new dependency.
- Apartments (`multifamily`) and `senior_housing` are never candidates.
- Every option shows this line verbatim: `Needs a call: owner permission; lot not verified clear`.
- Evidence is labelled by source: `CoStar:`, `Vexcel capture`, `Model reading:`.
- Threshold is `staging.min_surface_spaces`, value `100`, in `config/assumptions.yaml`, never a literal in code.
- Tests run with `.venv/bin/python -m pytest`; they use fixtures and no network.

## Review Focus

1. Vexcel has no tile for a lot: the option still shows, with `No aerial`. (Task 3 test, Task 4 card)
2. A property with no `buildingName` (most records): the address is used as the name. (Task 2 test)
3. An approved lot whose ZIP later gets an open request: it stays chosen and is marked `stale`. (Task 2 test, Task 4 card)
4. `lotSize` in square feet, an unknown unit, or missing; a parking row with a type and no count. (Task 1 tests)
5. No open request and no registered home, and a POST naming a building that is not a current option. (Task 2 and 3 tests)

---

### Task 1: Lot fields on the CoStar record

**Files:**
- Modify: `hearth/buildings/tools.py` (`normalize_costar`, `_costar_index`)
- Modify: `docs/toolkit-notes.md` (CoStar field map)
- Test: `tests/buildings/test_tools.py`

**Interfaces:**
- Produces: every normalized CoStar record has `surface_spaces: int | None` and `lot_acres: float | None`. Fixture records lack both keys, so readers use `.get`.

- [ ] **Step 1: Write the failing tests** (they use the existing `raw()` builder in this file)

```python
def test_normalize_reads_surface_spaces_and_lot_acres():
    n = tools.normalize_costar(raw(lotSize=9.5, lotSizeMeasurementType=2, parking=[
        {"parkingType": 1, "totalSpaces": 600}, {"parkingType": 1, "totalSpaces": 11}, {"parkingType": 3, "totalSpaces": 80}]))
    assert (n["surface_spaces"], n["lot_acres"]) == (611, 9.5)


def test_lot_in_square_feet_becomes_acres_and_unknowns_stay_none():
    assert tools.normalize_costar(raw(lotSize=87120, lotSizeMeasurementType=1))["lot_acres"] == 2.0
    assert tools.normalize_costar(raw(lotSize=5, lotSizeMeasurementType=0))["lot_acres"] is None
    n = tools.normalize_costar(raw(parking=[{"parkingType": 1}]))
    assert (n["surface_spaces"], n["lot_acres"]) == (None, None)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/buildings/test_tools.py -k "surface or square_feet" -v`. Expected: 2 FAIL with `KeyError: 'surface_spaces'`.

- [ ] **Step 3: Add the two fields to `normalize_costar`.** `surface_spaces` is the sum of `parking[].totalSpaces` where `parkingType == 1`, or `None` when no such row has a count. `lot_acres` is `lotSize` when `lotSizeMeasurementType == 2`, `lotSize / 43560` when it is `1`, else `None`; rounded to 2 places.

- [ ] **Step 4: Bump the index name.** In `_costar_index`, change `houston_v3.json` to `houston_v4.json` in both places (the local path and the `remote.fetch` path).

- [ ] **Step 5: Add two lines to the CoStar field map in `docs/toolkit-notes.md`:** surface parking (`parking[]` with `parkingType == 1`, `totalSpaces`; Houston: counts on 1,247 of 1,758) and lot size (`lotSize` with `lotSizeMeasurementType` 1 square feet / 2 acres; on 1,752).

- [ ] **Step 6: Run** `.venv/bin/python -m pytest tests/buildings -q`. Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add hearth/buildings/tools.py tests/buildings/test_tools.py docs/toolkit-notes.md docs/superpowers/specs/2026-11-14-staging-lots-design.md docs/superpowers/plans/2026-11-14-staging-lots.md
git commit -m "feat: surface parking and lot size on the CoStar record"
```

---

### Task 2: The staging rule and the dispatcher's choice

**Files:**
- Create: `hearth/staging.py`
- Modify: `config/assumptions.yaml` (new top-level `staging:` block)
- Test: `tests/test_staging.py`

**Interfaces:**
- Consumes: `tools.costar_all() -> list[dict]` (existing records only), `tools._km`, `dispatch.requests()`, `dispatch.LIVE`, `dispatch.person`, `dispatch.locate`, `store.get/put/delete/all`, `a("staging.min_surface_spaces")`.
- Produces, all in `hearth/staging.py`:
  - `candidates(rows: list[dict], dark_zips: set[str], center: tuple[float, float], limit: int = 3) -> list[dict]`
  - `scene() -> tuple[tuple[float, float], set[str]] | None` (centre and dark ZIPs, or `None` when there is nothing to centre on)
  - `options() -> list[dict]`
  - `chosen() -> dict | None`, `choose(building_id: str) -> dict` (raises `ValueError`), `clear() -> None`
  - An option is `{"building_id", "name", "address", "zip", "property_type", "surface_spaces", "lot_acres", "km"}`; `chosen()` adds `"stale": bool`.

- [ ] **Step 1: Add the config value**

```yaml
# ---- staging lots: where crews gather near an outage, proposed from CoStar parking data ----
staging:
  min_surface_spaces: {value: 100, source: "our call Nov 14: a surface lot this size leaves room for several vans; 131 non-apartment Houston properties in the kit pass", confirmed: false}
```

- [ ] **Step 2: Write the failing tests** in `tests/test_staging.py`

```python
"""Staging lots. Fixture world: every p* and demo-1 resident lives in B-SAMPLE (ZIP 77002)."""
import json

import pytest

from hearth import dispatch, staging, store
from hearth.buildings import tools
from hearth.config import ROOT
from hearth.contracts import Home, Patient

CENTER = (29.76, -95.37)


def lot(i, t="retail", spaces=300, zip="77027", lat=29.74, lon=-95.45, name=None):
    return {"building_id": i, "name": name, "address": f"{i} Lot St, Houston, TX {zip}", "zip": zip, "lat": lat, "lon": lon,
            "property_type": t, "surface_spaces": spaces, "lot_acres": 4.0}


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("HEARTH_FIXTURES", "1")
    monkeypatch.setenv("HEARTH_DB", str(tmp_path / "t.db"))
    for r in json.loads((ROOT / "data/demo/patients.json").read_text()):
        store.put("patient", r["patient_id"], Patient(**r))
    monkeypatch.setattr(dispatch, "_ask_model", lambda rows: json.dumps({"order": [{"patient_id": r["patient_id"], "reason": "x"} for r in rows]}))
    monkeypatch.setattr(tools, "costar_all", lambda: [lot("L1"), lot("L2", zip="77002")])


def test_only_big_non_apartment_lots_outside_the_dark_zips_qualify():
    rows = [lot("ok"), lot("apt", t="multifamily"), lot("senior", t="senior_housing"), lot("small", spaces=99),
            lot("unknown", spaces=None), lot("dark", zip="77002"), lot("nozip", zip=None), {"building_id": "old-fixture", "property_type": "hotel"}]
    assert [o["building_id"] for o in staging.candidates(rows, {"77002"}, CENTER)] == ["ok"]


def test_nearest_three_first_with_distance_and_a_name():
    rows = [lot("far", lat=29.95), lot("near", lat=29.77, lon=-95.37, name="Target"), lot("mid", lat=29.80), lot("farthest", lat=30.02)]
    out = staging.candidates(rows, set(), CENTER)
    assert [o["building_id"] for o in out] == ["near", "mid", "far"]
    assert (out[0]["name"], out[0]["km"]) == ("Target", 1.1)
    assert out[1]["name"] == "mid Lot St, Houston, TX 77027"  # no building name: the address stands in
    assert set(out[0]) == {"building_id", "name", "address", "zip", "property_type", "surface_spaces", "lot_acres", "km"}


def test_nothing_to_centre_on_means_no_options():
    assert staging.scene() is None and staging.options() == []


def test_with_no_open_request_registered_homes_set_the_centre_and_no_zip_is_dark():
    store.put("home", "p1", Home(patient_id="p1", building_id="B-SAMPLE", ok_without_h=4))
    assert [o["building_id"] for o in staging.options()] == ["L1", "L2"]


def test_options_avoid_a_requesters_zip_and_the_choice_is_kept():
    dispatch.open_request("demo-1")
    assert [o["building_id"] for o in staging.options()] == ["L1"]
    assert staging.choose("L1")["building_id"] == "L1"
    assert staging.chosen()["stale"] is False
    with pytest.raises(ValueError):
        staging.choose("L2")
    staging.clear()
    assert staging.chosen() is None


def test_a_chosen_lot_whose_zip_gets_a_request_is_marked_stale():
    store.put("staging", "current", lot("L2", zip="77002") | {"km": 1.0})
    dispatch.open_request("demo-1")
    assert staging.chosen()["stale"] is True
```

- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_staging.py -v`. Expected: collection error, `cannot import name 'staging'`.

- [ ] **Step 4: Write `hearth/staging.py`** to the signatures above.
  - `candidates`: keep rows whose `property_type` is not `multifamily` or `senior_housing`, whose `.get("surface_spaces")` is at least `a("staging.min_surface_spaces")`, and whose `zip` is set and not in `dark_zips`; sort by `tools._km(center, (lat, lon))`; `km` rounded to 1 place; `name` is the record's name or its address.
  - `scene`: the people behind requests in `dispatch.LIVE` states give the centre (mean lat and lon of `dispatch.locate`) and the dark ZIPs. With none, the people behind `store.all("home")` give the centre and the dark set is empty. With neither, `None`.
  - `options`: `candidates(tools.costar_all(), ...)` for the scene, `[]` without one.
  - `choose`: the option with that id from `options()`, stored with `store.put("staging", "current", option)`; `ValueError("not a current staging option")` otherwise.
  - `chosen`: the stored document plus `stale`, true when its `.get("zip")` is in the current scene's dark ZIPs (false without a scene).
  - `clear`: `store.delete("staging", "current")`.

- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_staging.py tests/test_dispatch.py -q`. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hearth/staging.py config/assumptions.yaml tests/test_staging.py
git commit -m "feat: staging lot rule over CoStar surface parking"
```

---

### Task 3: API routes, the lot tile and the lot reading

**Files:**
- Modify: `hearth/buildings/tools.py` (`vexcel_image`; new `LOT_QUESTION`, `lot_reading`)
- Modify: `api/main.py` (four routes; `_crew_view`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 2's `staging.options/chosen/choose/clear`.
- Produces:
  - `tools.vexcel_image(building_id, lat, lon, buffer_m: int = 40, name: str = "vexcel") -> Path | None` (file `<name>.png`; existing callers unchanged)
  - `tools.lot_reading(building_id: str, lat: float, lon: float) -> dict | None` returning `{"note": str}`, cached as layer `lot`; `None` in fixture mode
  - `GET /api/staging` -> `{"chosen": option | null, "options": [option]}`
  - `POST /api/staging` body `{"building_id": str | null}` -> `{"chosen": option | null}`; `null` clears the choice; 409 with the `ValueError` text
  - `GET /api/buildings/{building_id}/lot-image` -> PNG, 404 `no aerial image`
  - `GET /api/buildings/{building_id}/lot-reading` -> `{"note": str}`, 404 `no lot reading`
  - `GET /api/crews/{crew_id}/job` gains `"staging": option | null`

- [ ] **Step 1: Write the failing tests** in `tests/test_api.py`

```python
def test_staging_options_choice_and_clear(monkeypatch):
    from hearth import staging
    opt = {"building_id": "B-SAMPLE", "name": "Lot", "address": "1 Lot St", "zip": "77027", "property_type": "retail",
           "surface_spaces": 300, "lot_acres": 4.0, "km": 1.1}
    monkeypatch.setattr(staging, "options", lambda: [opt])
    monkeypatch.setattr(staging, "scene", lambda: None)
    client.post("/api/staging", json={"building_id": None})  # the test database outlives one test
    assert client.get("/api/staging").json() == {"chosen": None, "options": [opt]}
    assert client.post("/api/staging", json={"building_id": "NOPE"}).status_code == 409
    assert client.post("/api/staging", json={"building_id": "B-SAMPLE"}).json()["chosen"]["building_id"] == "B-SAMPLE"
    assert client.get("/api/staging").json()["chosen"]["stale"] is False
    assert client.post("/api/staging", json={"building_id": None}).json() == {"chosen": None}
    assert client.get("/api/staging").json()["chosen"] is None


def test_a_lot_without_a_tile_or_reading_is_404_not_an_error():
    assert client.get("/api/buildings/B-SAMPLE/lot-image").status_code == 404  # fixtures hold no lot tile
    assert client.get("/api/buildings/B-SAMPLE/lot-reading").status_code == 404  # fixtures ask no vision model
    assert client.get("/api/buildings/NOPE/lot-image").status_code == 404
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_api.py -k "staging or lot" -v`. Expected: the first test FAILS (404 on `/api/staging`). The second may already pass, because an unknown route is also a 404.

- [ ] **Step 3: Extend `vexcel_image`** with `buffer_m` and `name`; the cache and fixture paths use `f"{name}.png"` and the request sends `"buffer-meter": buffer_m`.

- [ ] **Step 4: Add `lot_reading`** next to `aerial_entrance`, same shape: `None` under fixtures; otherwise `cached(building_id, "lot", read)[0]`, where `read` takes `vexcel_image(building_id, lat, lon, 150, "lot")` and returns `{"note": look(img, LOT_QUESTION).strip()}`, or `None` without an image.

```python
LOT_QUESTION = (
    "This top-down aerial image is 300 m across with north up, centred on one commercial building. Where is its open "
    "surface parking, relative to the building, and from which side or street does a van drive in?")
```

- [ ] **Step 5: Add the routes to `api/main.py`**, after the refuge proposal routes. `lot-image` mirrors `building_image` with `(150, "lot")`. `lot-reading` mirrors `building_entrance`: any exception from the reading is treated as no reading. `_crew_view` returns `"staging": staging.chosen()` alongside `crew` and `job`.

- [ ] **Step 6: Run** `.venv/bin/python -m pytest -q`. Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add hearth/buildings/tools.py api/main.py tests/test_api.py
git commit -m "feat: staging lot API with a Vexcel lot tile and a cached reading"
```

---

### Task 4: The card on the dispatch page and the line on the crew page

**Files:**
- Create: `web/components/StagingCard.tsx`
- Modify: `web/lib/types.ts` (new `StagingLot`, `StagingView`; `CrewJob` gains `staging`)
- Modify: `web/app/dispatch/page.tsx` (render the card after the storm section)
- Modify: `web/app/responder/page.tsx` (one line)

**Interfaces:**
- Consumes: Task 3's routes.
- Produces:

```ts
export type StagingLot = { building_id: string; name: string; address: string; zip: string; property_type: string; surface_spaces: number; lot_acres: number | null; km: number; stale?: boolean };
export type StagingView = { chosen: StagingLot | null; options: StagingLot[] };
// CrewJob gains: staging: StagingLot | null;
```

- [ ] **Step 1: Add the types** to `web/lib/types.ts`.

- [ ] **Step 2: Write `StagingCard.tsx`**, a client component with no props. It polls `usePoll<StagingView>("/api/staging")`, keeps the index of the option on show in local state, shows the tile with `useAuthedImage("/api/buildings/<id>/lot-image")`, and reads `/api/buildings/<id>/lot-reading` with `getJson` when the option on show changes (a failed read shows no reading line). Use the dispatch page's card classes. Exact copy:
  - Heading, proposing: `Staging lot · proposed`. Heading, chosen: `Staging lot`.
  - Line 1: `{name} · {property_type} · {address} · {km} km from open requests` (omit `{address}` when it equals `{name}`).
  - Line 2: `CoStar: {surface_spaces} surface spaces · {lot_acres} acres · existing` (omit the acres part when null).
  - Tile alt text: `Aerial image of the lot, Vexcel`. Caption: `Vexcel aerial, 300 m across; capture date printed on the image`. No tile: `No aerial`.
  - Reading: `Model reading: {note}`.
  - Always: `Needs a call: owner permission; lot not verified clear`.
  - Buttons: `Approve` (POST, then `refresh`), `Next option` (cycles locally; hidden with one option).
  - Chosen: `Staging at {name}, {address} (not confirmed with the owner)` and a `Change` button (POST with `building_id: null`, then `refresh`). When `stale`: `A help request has opened in this lot's ZIP. Consider changing.`
  - No options and nothing chosen: `No lot to propose yet. A lot is proposed once a resident asks for help or registers a home.`
  - A failed POST shows the error text in the page's red (`#d03b3b`).

- [ ] **Step 3: Render `<StagingCard />`** in `web/app/dispatch/page.tsx` directly after the storm forecast section.

- [ ] **Step 4: Crew page.** In `web/app/responder/page.tsx`, where the crew is set up and not editing, show `Stage at {name}, {address} (not confirmed with the owner)` in the muted text style when `data.staging` is set.

- [ ] **Step 5: Run** `cd web && npm run lint && npx tsc --noEmit && npm test`. Expected: no errors, tests pass.

- [ ] **Step 6: Check it in the browser against the real data.** Start the API and web from the worktree, open `/dispatch`, open a help request as a demo resident on `/resident`, and confirm: a proposed lot appears with CoStar numbers and a real aerial tile; `Next option` changes the lot and the tile; `Approve` switches to the chosen line; `/responder` shows the `Stage at` line; `Change` returns to the proposal. Take a screenshot of the proposed card.

- [ ] **Step 7: Commit**

```bash
git add web/components/StagingCard.tsx web/lib/types.ts web/app/dispatch/page.tsx web/app/responder/page.tsx
git commit -m "feat: staging lot card on the dispatch page and a stage-at line for crews"
```

---

### Task 5: Ship it

Each step here leaves the machine; confirm with the user before running it.

- [ ] **Step 1: Upload the new index for the hosted API.** Running any building lookup once writes `data/buildings/_costar/houston_v4.json`. Then: `.venv/bin/python -m hearth.remote upload data/buildings/_costar/houston_v4.json costar/houston_v4.json` (needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`). Leave `houston_v3.json` in the bucket; the deployed `main` still reads it until this merges.
- [ ] **Step 2: Open a pull request** from `staging-lots` to `main`.
- [ ] **Step 3: After the merge, update the `main-preview` checkout** that serves `localhost:3000` and confirm the card there. That is where the user reviews.
