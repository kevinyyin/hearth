# Home Markup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A resident persona sets up their device and pins their home on the aerial image and the 3D scan; a responder persona sees that markup above the existing crew brief.

**Architecture:** One new document kind, `home`, in the existing store, behind four small API routes in `api/main.py`. Three new Next.js pages (`/start`, `/resident`, `/responder`) built from two pin components: one over the Vexcel image, one over the Matterport embed SDK. Personas are a browser-local choice; there is no login.

**Tech Stack:** FastAPI + pydantic, SQLite/Postgres document store (`hearth/store.py`), Next.js 15 + React 19 + Tailwind 4, vitest, Matterport Showcase embed SDK loaded from Matterport's own script URL.

**Spec:** `docs/superpowers/specs/2026-11-14-home-markup-design.md`

## Global Constraints

- Every resident is a synthetic patient from `data/demo/patients.json`. The "Simulated patients" badge in `web/app/layout.tsx` stays on every page. No real person's data.
- The scan is a sample unit. Wherever it is shown, the caption is exactly: `Sample unit from this building. The resident says their home is laid out like it.` (resident page: `Sample unit from this building, not your own home.`)
- No dispatch and no model call in this slice. No messaging.
- The `patient` record is not changed. All new data lives in the `home` document.
- No new dependencies in `pyproject.toml` or `web/package.json`.
- `MATTERPORT_SDK_KEY` reaches the browser only through the API response (already behind the password). It is never written to the repo, to a `NEXT_PUBLIC_*` variable, or to a log.
- The new pages need the live API. With `NEXT_PUBLIC_API` unset they show exactly: `This page needs the Hearth API.` and nothing else.
- Styling uses the existing CSS variables in `web/app/globals.css` (`--surface-0`, `--surface-1`, `--border`, `--text-*`). New pages are one column, `max-w-md`, centered.
- Work on a branch named `home-markup`, not on `main`.

## Browser checks

`.claude/launch.json` is git-ignored and local. The checks use three setups; run one web server at a time.

- **Real data:** the existing `api` (port 8001) and `web` (port 3000) entries. `demo-2` lives in building `23453`, which has four scans.
- **Fixture data:** add `HEARTH_WEB_ORIGINS=http://localhost:3001` to the `api-fixtures` entry's `env` arguments, and add an entry `web-fixtures`: `env NEXT_PUBLIC_API=http://localhost:8002 npm --prefix web run dev -- --port 3001`, port 3001. Fixture buildings have no real scan; `H-LEVEL` has no aerial image.
- **No scan key:** add an entry `api-nokey`: `env MATTERPORT_SDK_KEY= uv run uvicorn api.main:app --port 8001`, port 8001, used in place of `api`.

## Review Focus

1. **The pointer is on nothing.** Hovering sky, a window or outside the model reports `object !== "intersectedobject.model"` with positions thousands of metres away. No "Drop pin here" button may appear there. (Task 4 step 3; the API's ±1000 bound in Task 1 is the backstop.)
2. **The resident changes building or scan after placing pins.** Pins belong to the building and scan they were placed on, so they must be cleared, not carried over. (Task 2 `withBuilding`, `withScan` tests.)
3. **The building has no scan, or the API runs with fixtures.** `scan_ids` is empty: the inside section shows `No 3D scan for this building.` plus the note field, and Save still works. (Task 4 step 5 check.)
4. **The scan cannot open for the responder** (key missing, key refused, network). The job card must still show the inside pins as a text list and the note, with the line `The 3D scan did not open.`, never an empty box. (Task 4 step 3, Task 5 step 3 check.)
5. **No aerial image** (`/image` returns 404). The outside section shows `No aerial image for this building.`, places no pins, and Save still works. (Task 3 step 4 check.)

---

### Task 1: The `home` document and its API

**Files:**
- Modify: `hearth/contracts.py` (append after `RefugeProposal`)
- Modify: `hearth/buildings/tools.py` (next to `matterport_embed_url`)
- Modify: `api/main.py` (building detail; new section `# ---- home markup ----` before the refuge section)
- Modify: `docs/spec.md` (API table: four new rows)
- Test: `tests/test_home.py` (new)

**Interfaces:**
- Produces, in `hearth/contracts.py`:
  - `Vec3(x, y, z: float)`, each `Field(ge=-1000, le=1000)`
  - `OutsidePin(kind: Literal["park","entrance","blocked","route"], x: float, y: float)`, `x` and `y` `Field(ge=0, le=1)`
  - `InsidePin(kind: Literal["machine","blocked","route"], position: Vec3, normal: Vec3)`
  - `Home(patient_id: str, building_id: str, ok_without_h: float [0..720], backup_plan: str = "" [max 500], size: Literal["shoebox","microwave","carry_on","mini_fridge","custom"], size_cm: tuple[float, float, float] | None = None, scan_id: str | None = None, note: str = "" [max 500], outside: list[OutsidePin] = [] [max 50], inside: list[InsidePin] = [] [max 50])`
  - `Home` model validator: `size == "custom"` requires `size_cm` with each value in 1..300; `inside` non-empty requires `scan_id`.
  - Route order is list order among pins of kind `route`. There is no order field.
- Produces, in `hearth/buildings/tools.py`: `matterport_scan_ids(building_id: str) -> list[str]` — `[]` when fixtures are on (fixture scans have no real model), else the CoStar record's `matterport_model_ids`.
- Produces, HTTP:
  - `GET /api/demo-patients` → `Patient[]` (the demo file; `[]` if absent)
  - `GET /api/patients/{patient_id}/home` → `{"patient": Patient, "home": Home | null}`; 404 unknown patient
  - `PUT /api/patients/{patient_id}/home`, body `Home` → the stored `Home`; 404 unknown patient; 400 `"patient id does not match"` when body and path differ; 422 `"no such building"`; 422 `"that scan is not one of this building's"`
  - `GET /api/homes` → `[{"home": Home, "patient": Patient, "address": str}]`, oldest save first; a home whose patient or building no longer resolves is skipped
  - `GET /api/buildings/{id}` gains `"scan_ids": list[str]` and `"scan_sdk_key": str | None` (from `MATTERPORT_SDK_KEY`; `None` when unset or empty)

- [ ] **Step 1: Write the failing tests** in `tests/test_home.py`. Copy the `client` and the autouse `isolated` fixture from `tests/test_api.py` (without the refuge line). Imports: `pytest`, `TestClient`, `api.main.app`, `hearth.store`, `hearth.buildings.tools`.

```python
HOME = {"patient_id": "demo-1", "building_id": "B-SAMPLE", "ok_without_h": 4, "backup_plan": "spare battery", "size": "microwave",
        "scan_id": None, "note": "bedroom at the back",
        "outside": [{"kind": "park", "x": 0.25, "y": 0.5}, {"kind": "route", "x": 0.3, "y": 0.6}], "inside": []}
INSIDE = [{"kind": "machine", "position": {"x": 2.9, "y": 0.7, "z": 0.16}, "normal": {"x": 0, "y": 1, "z": 0}}]
put = lambda body, pid="demo-1": client.put(f"/api/patients/{pid}/home", json=body)


def test_home_round_trip_and_replace():
    assert client.get("/api/patients/demo-1/home").json()["home"] is None
    assert put(HOME).status_code == 200
    got = client.get("/api/patients/demo-1/home").json()
    assert got["home"]["outside"][1] == {"kind": "route", "x": 0.3, "y": 0.6} and got["patient"]["device"] == "feeding_pump"
    put(HOME | {"note": "moved to the den"})
    assert client.get("/api/patients/demo-1/home").json()["home"]["note"] == "moved to the den"
    assert store.get("patient", "demo-1")["backup_hours_on_hand"] == 4.0  # the patient record is untouched


@pytest.mark.parametrize("bad", [
    {"outside": [{"kind": "park", "x": 1.2, "y": 0.5}]},
    {"outside": [{"kind": "door", "x": 0.2, "y": 0.5}]},
    {"outside": [{"kind": "park", "x": 0.1, "y": 0.1}] * 51},
    {"size": "custom"},
    {"size": "custom", "size_cm": [40, 0, 30]},
    {"inside": INSIDE},  # inside pins with no scan chosen
    {"ok_without_h": -1},
])
def test_home_validation(bad):
    assert put(HOME | bad).status_code == 422


def test_scan_must_belong_to_the_building(monkeypatch):
    monkeypatch.setattr(tools, "matterport_scan_ids", lambda b: ["m1", "m2"])
    assert put(HOME | {"scan_id": "zzz"}).status_code == 422
    far = [{"kind": "machine", "position": {"x": 4344.1, "y": -6955.9, "z": 0}, "normal": {"x": 0, "y": 1, "z": 0}}]
    assert put(HOME | {"scan_id": "m2", "inside": far}).status_code == 422
    assert put(HOME | {"scan_id": "m2", "inside": INSIDE}).json()["inside"][0]["kind"] == "machine"


def test_unknown_patient_building_and_mismatched_id():
    assert put(HOME | {"patient_id": "nobody"}, pid="nobody").status_code == 404
    assert put(HOME | {"building_id": "NOPE"}).status_code == 422
    assert put(HOME, pid="demo-2").status_code == 400


def test_homes_list_demo_patients_and_building_detail():
    put(HOME)
    row = client.get("/api/homes").json()[0]
    assert row["home"]["patient_id"] == "demo-1" and row["patient"]["mobility"] == "wheelchair_power"
    assert row["address"] == client.get("/api/buildings/B-SAMPLE").json()["address"]
    demo = client.get("/api/demo-patients").json()
    assert {"demo-1", "demo-2"} <= {p["patient_id"] for p in demo} and all(p["synthetic"] for p in demo)
    d = client.get("/api/buildings/B-SAMPLE").json()
    assert d["scan_ids"] == [] and "scan_sdk_key" in d
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_home.py -q`
Expected: every test fails (404 on the new routes, `ImportError`/`AttributeError` for the new names).

- [ ] **Step 3: Add the contracts** to `hearth/contracts.py` exactly as listed under Interfaces.

- [ ] **Step 4: Add `matterport_scan_ids`** to `hearth/buildings/tools.py`.

- [ ] **Step 5: Add the routes** to `api/main.py`. Reuse `_patient` and `_building` for lookups (turn `_building`'s 404 into the 422 above on PUT). Store with `store.put("home", patient_id, body)`; read with `store.get` / `store.all("home")` and validate through `Home.model_validate` on the way out.

- [ ] **Step 6: Run the whole Python suite**

Run: `uv run pytest -q`
Expected: all pass, including the existing 203.

- [ ] **Step 7: Add four rows** to the API table in `docs/spec.md` for the routes above, and commit.

```bash
git add hearth/contracts.py hearth/buildings/tools.py api/main.py tests/test_home.py docs/spec.md
git commit -m "feat(api): home markup document, demo patients list, scan ids on building detail"
```

---

### Task 2: Web types, helpers and the shared image hook

**Files:**
- Modify: `web/lib/types.ts` (append)
- Modify: `web/lib/api.ts` (add `putJson`)
- Create: `web/lib/home.ts`
- Create: `web/lib/useAuthedImage.ts`
- Modify: `web/components/BuildingPanel.tsx` (replace its inline aerial-image effect with the hook)
- Test: `web/lib/home.test.ts` (new)

**Interfaces:**
- Produces, in `web/lib/types.ts`: `Vec3`, `OutsidePin`, `InsidePin`, `Home`, `OutsideKind`, `InsideKind`, `SizeId` mirroring Task 1; `Patient` (the fields of `hearth/contracts.py` `Patient`); `HomeRow = { home: Home; patient: Patient; address: string }`; `BuildingDetail` gains `scan_ids: string[]` and `scan_sdk_key: string | null`.
- Produces, in `web/lib/api.ts`: `putJson<T>(path: string, body: unknown): Promise<T>` — same header, 401 and error handling as the `fetch` in `web/components/ProposalCard.tsx`; throws `Error("This page needs the Hearth API.")` when `API` is empty.
- Produces, in `web/lib/home.ts`:
  - `SIZES: Record<Exclude<SizeId, "custom">, { label: string; cm: [number, number, number] }>` with exactly: `shoebox` "Shoebox" `[35, 20, 13]`; `microwave` "Microwave" `[50, 40, 30]`; `carry_on` "Carry-on suitcase" `[55, 35, 23]`; `mini_fridge` "Mini fridge" `[50, 50, 85]`
  - `PIN_LABEL: Record<OutsideKind | InsideKind, string>`: `park` "Park here", `entrance` "Entrance", `blocked` "Blocked", `route` "Route", `machine` "Machine"
  - `PIN_COLOR: Record<OutsideKind | InsideKind, string>`: `park` `#2a78d6`, `entrance` `#1baf7a`, `blocked` `#d03b3b`, `route` `#eda100`, `machine` `#8a4fd6`
  - `pinLabels(pins: { kind: string }[]): string[]` — the label per pin; route pins are numbered in list order ("Route 1", "Route 2")
  - `tapToFraction(tap: { clientX: number; clientY: number }, rect: { left: number; top: number; width: number; height: number }): { x: number; y: number }` — clamped to 0..1
  - `emptyHome(patient: Patient): Home` — the patient's own `building_id` (or `""`), `ok_without_h: 0`, `size: "microwave"`, no scan, no pins
  - `withBuilding(home: Home, buildingId: string): Home` and `withScan(home: Home, scanId: string | null): Home` — return the same object when nothing changes
  - `getPersona(): Persona | null`, `setPersona(p: Persona | null): void`, `type Persona = { role: "resident" | "responder"; id: string }`, stored under the local-storage key `hearth-persona`
- Produces, in `web/lib/useAuthedImage.ts`: `useAuthedImage(path: string | null): string | null` — the object URL of `${API}${path}` fetched with `authHeaders()`, `null` while loading or on failure, revoked on cleanup. This is the effect now inline in `BuildingPanel.tsx`, moved.

- [ ] **Step 1: Write the failing tests** in `web/lib/home.test.ts` (stub `localStorage` the way `web/lib/api.test.ts` does).

```ts
const home: Home = { patient_id: "demo-2", building_id: "23453", ok_without_h: 6, backup_plan: "", size: "microwave", size_cm: null,
  scan_id: "m1", note: "", outside: [{ kind: "park", x: 0.2, y: 0.2 }],
  inside: [{ kind: "machine", position: { x: 1, y: 1, z: 1 }, normal: { x: 0, y: 1, z: 0 } }] };

it("turns a tap into a fraction of the image, clamped", () => {
  const rect = { left: 100, top: 50, width: 200, height: 120 };
  expect(tapToFraction({ clientX: 150, clientY: 80 }, rect)).toEqual({ x: 0.25, y: 0.25 });
  expect(tapToFraction({ clientX: 50, clientY: 500 }, rect)).toEqual({ x: 0, y: 1 });
});
it("numbers route pins in order and names the rest", () => {
  expect(pinLabels([{ kind: "park" }, { kind: "route" }, { kind: "blocked" }, { kind: "route" }]))
    .toEqual(["Park here", "Route 1", "Blocked", "Route 2"]);
});
it("drops pins that belong to another building", () => {
  expect(withBuilding(home, "23453")).toBe(home);
  expect(withBuilding(home, "23347")).toMatchObject({ building_id: "23347", scan_id: null, outside: [], inside: [] });
});
it("drops inside pins that belong to another scan", () => {
  expect(withScan(home, "m1")).toBe(home);
  const next = withScan(home, null);
  expect(next.inside).toEqual([]); expect(next.scan_id).toBeNull(); expect(next.outside).toHaveLength(1);
});
it("keeps the persona in this browser", () => {
  expect(getPersona()).toBeNull();
  setPersona({ role: "resident", id: "demo-2" });
  expect(getPersona()).toEqual({ role: "resident", id: "demo-2" });
  setPersona(null); expect(getPersona()).toBeNull();
});
it("knows the carry-on size", () => expect(SIZES.carry_on.cm).toEqual([55, 35, 23]));
```

- [ ] **Step 2: Run and see them fail**

Run: `cd web && npm test -- home`
Expected: FAIL, cannot resolve `./home`.

- [ ] **Step 3: Write `types.ts` additions, `putJson`, `home.ts`, `useAuthedImage.ts`,** and switch `BuildingPanel.tsx` to the hook.

- [ ] **Step 4: Run tests and the type check**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: all tests pass (the existing 26 plus 6), no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/lib web/components/BuildingPanel.tsx
git commit -m "feat(web): home markup types and helpers; aerial image fetch as a hook"
```

---

### Task 3: Start page, and the resident page up to the outside pins

**Files:**
- Create: `web/components/AerialPins.tsx`
- Create: `web/app/start/page.tsx`
- Create: `web/app/resident/page.tsx`
- Modify: `web/app/page.tsx:170` (add a `Switch role` link to `/start` beside `Results`)

**Interfaces:**
- Consumes: everything Task 2 produces; `GET /api/demo-patients`, `GET`/`PUT /api/patients/{id}/home`, `GET /api/buildings`, `GET /api/buildings/{id}` from Task 1.
- Produces: `AerialPins({ imagePath, pins, kind, onChange }: { imagePath: string; pins: OutsidePin[]; kind?: OutsideKind; onChange?: (pins: OutsidePin[]) => void })`. Read-only when `onChange` is absent. Task 5 uses it read-only.
- Produces: `/resident` holds its form in one `Home` state and renders an `Inside` section placeholder that Task 4 fills.

- [ ] **Step 1: `AerialPins`.** The image comes from `useAuthedImage(imagePath)`. Pins are absolutely positioned buttons at `left: x*100%`, `top: y*100%`, colored by `PIN_COLOR`, labelled by `pinLabels` (as `aria-label` and as a short visible caption). Route pins are joined in order by an SVG polyline over the image. Editable: a tap on the image appends `{ kind, ...tapToFraction(...) }` unless 50 pins exist; a tap on a pin removes it. No image: render `No aerial image for this building.`

- [ ] **Step 2: `/start`.** Three cards. **Resident**: one button per demo patient, text `{patient_id} · {device} · {mobility}` with underscores shown as spaces; a press calls `setPersona({ role: "resident", id })` and goes to `/resident`. **Responder**: a `Crew name` text field and `Continue`; a press calls `setPersona({ role: "responder", id: name })` and goes to `/responder`; empty names are refused. **Dispatcher**: a link to `/`. Heading: `Who are you?` Sub-line: `Demo personas over simulated patients. Nothing here is a real account.`

- [ ] **Step 3: `/resident`.** No resident persona: `router.replace("/start")`. Otherwise load `GET /api/patients/{id}/home`; start from the saved `home` or `emptyHome(patient)`. Sections, in order, each with its heading:
  1. `Your device` — the patient's device (read-only text); number field `Without it I'm OK for … hours`; text field `Backup plan`; `About the size of` as four toggle buttons from `SIZES` plus `Other`, which reveals three number fields `Width`, `Depth`, `Height` in cm and sets `size: "custom"`.
  2. `Your building` — a search field filtering `GET /api/buildings` by case-insensitive substring of `address` or `name`, showing at most 8 matches; choosing one applies `withBuilding`. The current building's address is shown above the field. If the patient's building does not resolve (404), show only the search.
  3. `Outside` — a row of four kind buttons (`Park here`, `Entrance`, `Blocked`, `Route`), then `AerialPins` in edit mode with the building's `image_url`. Helper text: `Pick what to mark, then tap the image. Tap a pin to remove it.`
  4. `Inside` — placeholder `<section>` for Task 4.
  5. A `Save` button: `putJson`, then the line `Saved.`; on failure the error's message in `#d03b3b`.

- [ ] **Step 4: Check it in the browser,** real-data setup. At `/start` choose `demo-2`; on `/resident` set 6 hours, pick `Carry-on suitcase`, place one `Park here`, one `Entrance` and three `Route` pins, save, reload.
Expected: the pins and answers come back; the route is numbered 1 to 3 and joined by a line. Then, on the fixture setup, open `/resident` as `demo-1` and choose `H-LEVEL` in the building search: the outside section reads `No aerial image for this building.` and Save still succeeds.

- [ ] **Step 5: Type check and commit**

Run: `cd web && npx tsc --noEmit && npm test`
Expected: clean.

```bash
git add web/app web/components/AerialPins.tsx
git commit -m "feat(web): persona start page; resident device setup and outside pins"
```

---

### Task 4: Pins inside the 3D scan

**Files:**
- Create: `web/components/ScanPins.tsx`
- Modify: `web/app/resident/page.tsx` (fill the `Inside` section)

**Interfaces:**
- Consumes: `InsidePin`, `InsideKind`, `PIN_COLOR`, `pinLabels`, `withScan` from Task 2; `scan_ids` and `scan_sdk_key` on building detail from Task 1.
- Produces: `ScanPins({ scanId, sdkKey, pins, kind, onChange }: { scanId: string; sdkKey: string | null; pins: InsidePin[]; kind?: InsideKind; onChange?: (pins: InsidePin[]) => void })`. Read-only when `onChange` is absent. Task 5 uses it read-only.

Facts about the embed SDK, verified on Nov 14 against the first scan of building `23453`; the builder cannot derive these:

```ts
// script, loaded once per page: https://static.matterport.com/showcase-sdk/latest.js  → window.MP_SDK
iframe.src = `https://my.matterport.com/show?m=${scanId}&play=1&qs=1&applicationKey=${sdkKey}`;
// on the iframe's load event:
const sdk = await window.MP_SDK.connect(iframe, sdkKey, "");
await sdk.App.state.waitUntil((s) => s.phase === sdk.App.Phase.PLAYING);   // 10 to 20 s on a cold load
const [id] = await sdk.Tag.add({ label, description: "", anchorPosition: pin.position,
  stemVector: { x: n.x * 0.3, y: n.y * 0.3, z: n.z * 0.3 }, color: { r, g, b } });   // color channels 0..1
await sdk.Tag.remove(id);
sdk.Pointer.intersection.subscribe((i) => { /* i.position, i.normal, i.object */ });
// a real surface has i.object === "intersectedobject.model"; anything else is sky or outside the model
const p = sdk.Conversion.worldToScreen(i.position, await sdk.Camera.getPose(), { w: iframe.clientWidth, h: iframe.clientHeight });
```

- [ ] **Step 1: `ScanPins`, viewing.** A `relative` box, 16:10, holding the iframe (`allow="xr-spatial-tracking; fullscreen"`). Connect as above. The iframe `src` depends only on `scanId` and `sdkKey`; a change in `pins` must not reload it. Whenever `pins` change after connect, remove the tags this component added and add the current ones (labels from `pinLabels`, colors from `PIN_COLOR`). Below the box, always render the pins as a text list (`Machine`, `Route 1`, …). While loading: `Opening the 3D scan…`. If `sdkKey` is null, the script fails, `connect` rejects, or 30 s pass without `PLAYING`: `The 3D scan did not open.` and the text list stays.

- [ ] **Step 2: `ScanPins`, facing the machine (read-only mode).** After the tags are added, if a `machine` pin exists call `sdk.Mattertag.navigateToTag(id, sdk.Mattertag.Transition.FLY)` for its tag id inside a `try`. If the SDK rejects the call, leave the start view; record in the task report that it was rejected.

- [ ] **Step 3: `ScanPins`, editing.** Subscribe to the pointer. On every update hide the button and restart an 800 ms timer; when it fires and `i.object === "intersectedobject.model"`, show a `Drop pin here` button over the iframe at the `worldToScreen` point, shifted up by its own height. Pressing it appends `{ kind, position: i.position, normal: i.normal }` unless 50 pins exist. Each row of the text list gets a `Remove` button in edit mode. Helper text: `Hold the pointer still on the spot, then press "Drop pin here".`

- [ ] **Step 4: The resident `Inside` section.** Heading `Inside`. If the building's `scan_ids` is empty: `No 3D scan for this building.` and the `Note for the responder` text field. Otherwise the question `Which of these is laid out like your home?` with one button per scan (`Layout 1`, `Layout 2`, …, at most the first 6) and `None of these`; each choice applies `withScan`. With a scan chosen: the caption `Sample unit from this building, not your own home.`, three kind buttons (`Machine`, `Blocked`, `Route`), `ScanPins` in edit mode, then the note field. With `None of these`: only the note field.

- [ ] **Step 5: Check it in the browser,** real-data setup. As `demo-2`: choose `Layout 1`, wait for the scan, hold the pointer on the floor, press `Drop pin here` as `Machine`, add two `Route` pins, save, reload.
Expected: three tags in the scan and three rows in the list after the reload. Then hold the pointer on a window showing sky: no button appears. Then switch to `Layout 2`: the list empties. Then, on the fixture setup, open `/resident` as `demo-1`: `No 3D scan for this building.`, and Save succeeds.

- [ ] **Step 6: Type check and commit**

Run: `cd web && npx tsc --noEmit && npm test`
Expected: clean.

```bash
git add web/components/ScanPins.tsx web/app/resident/page.tsx
git commit -m "feat(web): pins inside the 3D scan for the resident"
```

---

### Task 5: The responder's job card

**Files:**
- Create: `web/app/responder/page.tsx`

**Interfaces:**
- Consumes: `GET /api/homes` (`HomeRow[]`), `GET /api/buildings/{id}` (`BuildingDetail`), `AerialPins` and `ScanPins` read-only, the existing `AccessBrief` component, `SIZES`, `getPersona`.

- [ ] **Step 1: The list.** No responder persona: `router.replace("/start")`. Heading `Jobs` with the crew name. One row per `HomeRow`: `{patient_id} · {device} · {address}`. No rows: `No resident has marked up a home yet.` Selecting a row opens its card below the list.

- [ ] **Step 2: The card,** in this order:
  1. `{device}` and `{mobility}` from the patient (underscores as spaces); `OK without it for {ok_without_h} hours`; `Size: {label} ({w} × {d} × {h} cm)` from `SIZES` or `size_cm`; `Backup plan: …` and `Resident's note: …` when non-empty.
  2. `Outside` — `AerialPins` read-only.
  3. `Inside` — with a `scan_id`: `ScanPins` read-only and the caption `Sample unit from this building. The resident says their home is laid out like it.` Without: `The resident did not match a scan to their home.`
  4. The existing `<AccessBrief brief={detail.brief} />` when the building has one.

- [ ] **Step 3: Check the whole flow in the browser,** real-data setup, the home saved in Task 4 still stored. `/start` → Responder, crew name `Medic 4` → the `demo-2` row → the card.
Expected: device, size and hours match what the resident entered; outside pins sit where they were placed; the scan opens with the three inside tags and turns toward the machine pin (or stays on its start view if Step 2 of Task 4 recorded a rejection). Then switch to the no-scan-key setup: the card reads `The 3D scan did not open.` and still lists the three pins.
Take one screenshot of the resident page and one of the job card for the report.

- [ ] **Step 4: Full checks and commit**

Run: `uv run pytest -q && cd web && npm test && npx tsc --noEmit && npm run lint`
Expected: all clean.

```bash
git add web/app/responder/page.tsx
git commit -m "feat(web): responder job card with the resident's home markup"
```
