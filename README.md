# Hearth

A dispatcher tool for people on power-dependent home medical devices during a multi-day outage.
It replays Hurricane Beryl (2024) over **simulated** Harris County patients, surveys their buildings
with a deep agent over CoStar, Vexcel and Matterport data, and proposes refuges a dispatcher must approve.
All patients are synthetic.

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
