# Dispatch command center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/dispatch` into one screen (county map with household pins, a rail of Needs you / Agents at work / Help in
progress / Crews) where the building survey and the refuge search start on their own and every control works.

**Architecture:** The server owns the agent runs: a stored `agent_run` record per building survey (`survey-<building>`)
and refuge search (`refuge-<patient>`), with step lines and result, written as the SSE stream is consumed, guarded
against a second start while one runs. `/api/dispatch` grows into the page's one poll: map positions, runs, which
runs to start (`to_start`), pending proposals and storm-round history. The page only starts what `to_start` lists and
reads everything else from polls, so every tab shows the same thing.

**Tech Stack:** FastAPI, pydantic, the JSON-doc store (`hearth/store.py`), Next.js App Router, React, Tailwind 4, MapLibre.

**Spec:** `docs/superpowers/specs/2026-11-14-dispatch-command-center-design.md` (with its "Builder questions settled"),
mockups `.superpowers/brainstorm/11988-1794705309/content/dispatch-hifi.html` and `dispatch-hifi-v2.html` (header).

## Global Constraints

- Households are named by address, never by patient ID.
- Pin colours: needs you `#c4461a`, waiting `#a87400`, crew on the way `#2a78d6`, safe `#0e7a54`, simulated `#a39c8c`.
- Shelter leads say "call to confirm"; a refuge's power is "not verified"; simulated households are labelled simulated.
- Every tunable number in `config/assumptions.yaml` with a `source` and `confirmed: false`.
- Agents run beside the rule-based path, never in front of it: the refuge agent only for requests blocked by `NO_REFUGE`.
- No real call or text in tests or checks; the store is a temp SQLite file (`HEARTH_DB`).
- Every button has a pending state that blocks double presses, and shows errors in plain words.

## Review Focus

- Two tabs open: the second start of the same run gets 409 and nothing runs twice (Task 1 test).
- A run cut off (tab closed, function timed out) must not block forever: a running record older than
  `agents.stale_after_s` counts as stopped and may start again (Task 1 test).
- A rejected proposal starts the refuge search again, once (Task 2 test).
- An approved proposal makes its first option the drop-off and a crew is offered (Task 3 test).
- A storm press inside the two-minute guard records no round (Task 4 test).

---

### Task 1: Agent runs (`hearth/agents.py`)

**Files:** Create `hearth/agents.py`; modify `api/main.py` (survey and propose endpoints), `config/assumptions.yaml`
(`agents.stale_after_s` 300, `agents.rail_min` 10, `agents.max_running` 2); test `tests/test_agents.py`.

**Interfaces — produces:**
- `claim(kind: Literal["survey","refuge"], *, building_id, patient_id, address) -> dict` raises `ValueError` while a
  fresh run with that id is running; stores `{run_id, kind, building_id, patient_id, address, status: "running",
  started_at, updated_at, steps: [], result: {}}` under kind `agent_run`.
- `track(run: dict, events: Iterator[TraceEvent]) -> Iterator[TraceEvent]`: passes events through, recomputes
  `steps` (`[{text, t0, t1}]`, seconds since start; `t1` None while live) and stores the record each event; at the
  end `status` is `done`/`failed` and `result` is `{proposal_id}` or `{shelter_sites, message}` or `{error}`;
  a stream closed early ends `stopped`. After a survey writes a profile, `dispatch.place_again`.
- `runs() -> list[dict]` with a running record past `stale_after_s` reported as `stopped`, each with `on_rail`.
- Endpoints answer 409 on a second start. A cached survey hit is passed through untracked.

- [ ] Tests: `test_second_start_while_running_is_refused`, `test_a_stale_run_may_start_again`,
  `test_track_stores_steps_and_result` (survey layer steps CoStar / Vexcel / Matterport close on their file event;
  refuge steps close when the next starts; done stores shelter sites), `test_survey_endpoint_409_while_running`.
- [ ] Implement, run `uv run pytest tests/test_agents.py -q`, commit.

### Task 2: What the page starts, and the dispatch view

**Files:** Modify `hearth/agents.py` (`to_start`), `api/main.py` (`/api/dispatch`, `/api/dispatch/simulated`),
`hearth/staging.py` (lat/lon on lots), config `dispatch_page.window_h` 24, `dispatch_page.simulated_runs`,
`dispatch_page.simulated_dots` 400; test `tests/test_agents.py`, `tests/test_help.py`.

**Interfaces — produces:** `to_start() -> list[{run_id, kind, building_id, patient_id, key}]`: a survey for each phone
registration whose building has no agent profile and no run except a stopped one; a refuge search for each waiting
request blocked by `NO_REFUGE` with no run, a stopped run, a run from an earlier request, or a run whose proposal was
rejected; capped at `agents.max_running` minus those running. `/api/dispatch` rows gain `patient`, `home`,
`building_id`, `lat`, `lon`; ended requests older than `window_h` drop off; the body gains `agents`, `to_start`,
`proposals` (pending) and `storm` (Task 4).

- [ ] Tests: `test_to_start_lists_unsurveyed_registrations_once`, `test_blocked_request_starts_one_refuge_search`,
  `test_rejected_proposal_starts_the_search_again`, `test_to_start_is_capped`, `test_dispatch_rows_carry_positions`,
  `test_simulated_dots_are_a_sample`.
- [ ] Implement, run tests, commit.

### Task 3: Approve makes the drop-off

**Files:** Modify `hearth/contracts.py` (`HelpRequest.refuge_pick: RefugeOption | None = None`), `hearth/dispatch.py`
(`use_refuge(patient_id, option)`; `run()` prefers `refuge_pick`), `api/main.py` (decision endpoint), `web/lib/types.ts`;
test `tests/test_help.py`.

- [ ] Test `test_approving_a_proposal_makes_it_the_drop_off_and_offers_a_crew`: blocked p1-style request, approve,
  request is `offered` with `refuge.building_id == "H-LEVEL"`.
- [ ] Implement, run, commit.

### Task 4: Storm-round history and the reset

**Files:** Modify `hearth/messaging/registry.py` (`storm` stores `storm/<round>` = `{round, t, dialed, failed}`;
`storm_history() -> {placed: {round: t}, last: {round, t, dialed, failed, registered} | None}` counting registrations by
calls with `ctx.storm == round` since `t`); `hearth/store.py` (`clear(kind)`); create `hearth/reset.py`
(`python -m hearth.reset --yes`: clears help, call, agent_run, storm, proposal, and the demo numbers' registrations;
without `--yes` it prints what it would clear); tests in `tests/messaging/test_registry.py`, `tests/test_store.py`.

- [ ] Tests: `test_a_round_is_remembered_with_its_counts`, `test_a_guarded_press_records_no_round`,
  `test_reset_clears_demo_state`, `test_store_clear`.
- [ ] Implement, run, commit.

### Task 5: The page

**Files:** Rewrite `web/app/dispatch/page.tsx`; create `web/components/DispatchMap.tsx`, `web/components/HouseholdCard.tsx`,
`web/lib/dispatch.ts` (+ `dispatch.test.ts`: `pinState`, `households` merge, `stepSeconds`); modify `ProposalCard.tsx`
(title prop, reason asked on Reject, rail styling), `StagingCard.tsx` (one lot as a prop, Choose / Clear),
`BuildingPanel.tsx` (proposal goes to the dispatch page), `Map.tsx` (export `STYLE_URL`), `web/lib/types.ts`.

- [ ] Header per v2 mockup: "Call everyone on the list", three tiles with arrows, last-round line.
- [ ] Map: faint simulated dots, labelled household pins by state, outlined/solid "P" lot pins, fit with right padding.
- [ ] Card: from the call, the building with source chips (or "Agents researching…"), where to take them (refuge,
  or reason + leads), Take over, Open the floor plan; close button; "See leads" scrolls to leads.
- [ ] Rail: Needs you, Agents at work, Help in progress, Crews. Page starts each `to_start` item once per key.
- [ ] `npx tsc --noEmit`, `npx vitest run`, detector, browser check at 1440 and 375, commit.
