# Hearth

**Keeps people on home oxygen, ventilators and other powered medical devices alive through a multi-day blackout.**
Hearth gives each patient a plan, checks in on them by phone, ranks who needs help first, and sends crews to them,
handing every uncertain call to a human.

[▶ Demo video](https://www.youtube.com/watch?v=_B6XLNeXfDk) · [Live app](https://hearth-seven-chi.vercel.app) · [Devpost](https://devpost.com/software/hearth-n8twj0)

Built at HackPrinceton Fall '26 by Kevin Yin, Raina Ban, James Wang and Jade Gu. Kevin wrote most of the code
(226 of the repo's 271 commits).

> All patients and callers are **simulated**, built from public Hurricane Beryl (2024) data. No real patients were involved.

## The problem

When the power goes out for days, emergency teams usually don't know who in the dark area depends on a powered medical
device, how long each person's backup will last, or who to reach first. We interviewed 6 Texas first responders and
dispatchers during the hackathon; the gap they described is information at scale, not willingness to help.

## What it does

- **A countdown for every patient.** How long their device's backup lasts, and how long until a hot home becomes unsafe.
- **Phone check-ins.** An AI voice agent calls each patient (3 rounds), reads back battery hours and whether they need help now,
  and hands off to a human after one clarifying question, or after three silences. Silence never counts as "safe".
- **Dispatch.** Crews are matched to requests with the Hungarian algorithm; a central planner re-plans across the whole county.
- **Relocation.** A building agent surveys candidate refuges (CoStar, Vexcel, Matterport) for step-free access, and a dispatcher approves each move.

**The rule behind every part: the model reads and interprets; code decides and speaks.** The phone agent can only say lines
allowed for the patient's current state, so it never says "a crew is coming" before a crew has accepted.

## Results

Hurricane Beryl replay: 647 simulated Harris County patients, real EAGLE-I outage data every 15 minutes, 20 crews,
median of 100 seeded runs vs. a modeled phone tree ([`results/sweep_beryl_2024.json`](results/sweep_beryl_2024.json)):

| | Phone tree | Hearth | Hearth + central planner |
|---|---|---|---|
| Devices that ran out at home | 383 | 184 | **11** |
| Risk-weighted patient-hours at risk | 43,841 | 5,104 (−88%) | **208 (−99.5%)** |

Phone agent on 58 scripted caller turns ([`evals/report.md`](evals/report.md)):

| Measure | Result |
|---|---|
| Escalated when it should have (recall) | 86% (24 of 28) |
| Escalations that were needed (precision) | 83% (24 of 29) |
| Backup hours read within 10% | 28 of 30 |
| "Needs help now" read correctly | 8 of 8 |
| Planted attempts to make it say something unsafe | 20 of 20 blocked |
| Median reply time | 1.98 s |

**Known misses:** "about 40 hours" was taken at face value when the caller meant 4; vague answers ("the tank's maybe a third gone")
didn't always escalate; suspicious callers were over-escalated. A fancier multi-stop route search (ALNS) did not clearly beat
simple pairing, so we report that rather than claim it.

## How it's built

Python, FastAPI, Next.js/React, MapLibre · LangChain deepagents on Claude (Sonnet coordinator, Haiku subagents and call
interpreter) · ElevenLabs voice, Photon for phone/iMessage · CoStar, Vexcel and Matterport building data · Supabase, Vercel.

## Setup

```bash
uv sync
cp .env.example .env   # fill in keys; never commit .env
uv run pytest          # live tests are skipped; run them with -m live
```

`HEARTH_FIXTURES=1` makes the building tools read `data/buildings/_fixtures/` instead of the sponsor APIs.
Every default number is in `config/assumptions.yaml` with its source. Plan and design: `docs/superpowers/`.

Only `main` deploys to Vercel (`git.deploymentEnabled` in `vercel.json` and `web/vercel.json`). Both projects share one
account's deployment limit, so branches get no preview URL; check a branch locally. A branch cut before this landed
still deploys on every push until it merges `main`.

Run the API (the map reads it at `http://localhost:8000`):

```bash
uv run uvicorn api.main:app --port 8000
```

## Reproduce the results

Every number on the results page comes from these commands (patients are synthetic; sponsor data stays local):

```bash
uv run python scripts/fetch_data.py --scenario beryl_2024             # public data: emPOWER, EAGLE-I, MCC, IAH weather, ZCTA
uv run python -m hearth.buildings bulk                                # records-only building profiles (needs the CoStar kit and Vexcel key)
uv run python -m hearth.sim sweep --scenario beryl_2024               # writes results/sweep_beryl_2024.json (crews and seeds from assumptions.yaml)
uv run python -m hearth.sim run --scenario beryl_2024 --policy p3 --seed 1 --crews 20   # the map's county replay (about 350 MB, git-ignored)
```

The sweep copies `config/assumptions.yaml` next to its results. Caveats are listed on the results page and in `docs/sim-notes.md`.
