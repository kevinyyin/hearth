"""Clears the demo state so a rehearsal starts clean: help requests, call records, agent runs, storm-round history,
refuge proposals, and the registrations the demo numbers (HEARTH_DEMO_CALLERS) made. Building profiles, crews, the
staging lot and the agent's memory of rejections stay.

python -m hearth.reset          says what it would clear, and where
python -m hearth.reset --yes    clears it
"""
import os
import sys

from hearth import store
from hearth.messaging import registry

KINDS = ("help", "call", "agent_run", "storm", "proposal")


def reset() -> dict:
    out = {k: len(store.all(k)) for k in KINDS}
    for k in KINDS:
        store.clear(k)
    out["registrations"] = sum(registry.reset(phone) for phone in sorted(registry.demo_callers()))
    return out


def main(argv: list[str]) -> None:
    where = "the Postgres store (HEARTH_DATABASE_URL)" if store.postgres_url() else f"the SQLite store {os.environ.get('HEARTH_DB', 'data/hearth.db')}"
    if "--yes" not in argv:
        counts = {k: len(store.all(k)) for k in KINDS}
        print(f"Would clear from {where}: {counts}, and the registrations of {sorted(registry.demo_callers())}. Run again with --yes.")
        return
    print(f"Cleared from {where}: {reset()}")


if __name__ == "__main__":
    main(sys.argv[1:])
