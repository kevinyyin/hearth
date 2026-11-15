# Algorithm, technical version: design

## Intent
A second Algorithm page for the CoStar track judges: shorter and more technical than `/algorithm`, built around the data
stack (CoStar, Vexcel, Matterport, LangChain deepagents), and showing real data rather than describing it. The current
`/algorithm` page stays as it is.

## Goals
- Lead with CoStar: what record fields Hearth reads and what each one changes in the plan.
- Show one real building's surveyed profile live from the API: every field with its source layer and confidence, the
  conflicts the agent found between layers, and how many hours of heat deadline each layer moves.
- Let a judge run the surveyor deep agent live and watch its plan, three parallel subagents and conflict follow-ups.

## Non-goals
- No sliders or interactive solver demos (those stay on `/algorithm`).
- No new API routes; no change to the banner.

## Approaches
1. Static page written from the code: fast and unbreakable, but shows field names only.
2. **Live page on the existing building API (picked by the user):** most convincing; depends on the API while judges click.
3. A technical toggle on `/algorithm`: rejected, it changes the page the user wants kept.

## Design
- Route `/algorithm/technical`. Same banner, Algorithm marked current. `/algorithm` gets a small "Technical version →"
  link; the new page links back with "Interactive version →".
- Hero: one line, then four figures: 1,758 Houston CoStar records, 1,732 with a Matterport scan, 4 Vexcel endpoints,
  3 parallel subagents.
- **Live building** (client, through the password like every page): chips for the buildings with a stored agent survey
  (`GET /api/buildings`, `surveyed`), default Calais Midtown Apartments (7768847: all three layers, 2 conflicts). For the
  chosen one, `GET /api/buildings/{id}`:
  - profile table: field (mono) · value · source · confidence; unknown fields collapsed into one line;
  - conflicts, verbatim;
  - layer effects: hours to unsafe with every layer, and with each layer's fields reset (`layer_effects`), as bars;
  - the Vexcel tile (`image_url` via `useAuthedImage`).
  - **Replay at 2× (user decision, Nov 15):** a real survey took 35 s locally, too long for judges. Every live survey
    that finishes now stores its events (`survey_recording`, written in `agents.track`), and
    `GET /api/buildings/{id}/survey/recording` serves the last one. The page plays it back at twice its recorded
    timing (~18 s), labeled with when it ran and how long it took live.
  - "Run it live" streams `GET /api/buildings/{id}/survey?fresh=true` into the same log and `AgentTrace`, then
    reloads the profile and the recording. A 409 (already running) or failure shows its message; the stored profile is
    only replaced when the agent writes a new one.
- **Static, always rendered** (so the page still reads if the API is down):
  - pipeline: `commercial-property.jsonl` → `normalize_costar` → surveyor (costar / aerial / interior subagents) →
    `BuildingProfile {value, source, confidence}` → planner;
  - CoStar field map, ~10 rows: CoStar field → Hearth field → what it drives;
  - surveyor rules (CoStar is the authority on elevators; no field without a layer; derived numbers computed by code);
  - refuge agent in one line; Vexcel and Matterport calls, one line each;
  - planner in four lines (score, Hungarian pairing, ALNS routes, Dijkstra indoors); three limits.

## Left to the builder
Layout and wording within the site's paper look; component split; which unknown fields to list.
