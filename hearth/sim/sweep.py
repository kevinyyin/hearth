"""Crew-count sweep: every policy x crew count x seed in a process pool, aggregated for the results chart."""
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from hearth.config import ASSUMPTIONS, ROOT
from hearth.metrics import sweep_rows
from hearth.planner import Flags
from hearth.sim.engine import policy_label, run

SWEEP = [("p0", Flags()), ("p3", Flags()), ("p3", Flags(use_buildings=False)), ("p3", Flags(allow_moves=False)),
         ("p3", Flags(mutual_aid=True)), ("p3", Flags(routing="paired")), ("p3", Flags(routing="alns"))]


def _one(job: tuple) -> dict:
    scenario, policy, flags, crews, seed = job
    s = run(scenario, policy, seed, crews, flags, out_root=None)
    return {"policy": policy_label(policy, flags), "crews": crews, "seed": seed, **s}


def sweep(scenario: str, crews: list[int], seeds: int, out_root: Path = ROOT / "results") -> list[dict]:
    """Every policy x crew count x seed 1..seeds, in a process pool; writes sweep_<scenario>.json and the assumptions used."""
    jobs = [(scenario, p, f, c, s) for p, f in SWEEP for c in crews for s in range(1, seeds + 1)]
    with ProcessPoolExecutor() as pool:
        rows = sweep_rows(list(pool.map(_one, jobs)))
    Path(out_root).mkdir(parents=True, exist_ok=True)
    (Path(out_root) / f"sweep_{scenario}.json").write_text(json.dumps(rows, indent=1))
    shutil.copyfile(ASSUMPTIONS, Path(out_root) / f"sweep_{scenario}.assumptions.yaml")
    return rows
