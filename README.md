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

Run the API (the map reads it at `http://localhost:8000`):

```bash
uv run uvicorn api.main:app --port 8000
```
