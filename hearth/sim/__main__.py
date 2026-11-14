"""python -m hearth.sim run --scenario beryl_2024 --policy p3 --seed 1 --crews 20 [--no-buildings] [--no-moves] [--mutual-aid]"""
import argparse
import json

from hearth.planner import Flags
from hearth.sim.engine import run


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m hearth.sim")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one run; writes results/<run_id>/")
    r.add_argument("--scenario", default="beryl_2024")
    r.add_argument("--policy", choices=["p0", "p3"], default="p3")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--crews", type=int, default=20)
    r.add_argument("--no-buildings", action="store_true")
    r.add_argument("--no-moves", action="store_true")
    r.add_argument("--mutual-aid", action="store_true")
    args = p.parse_args(argv)
    flags = Flags(use_buildings=not args.no_buildings, allow_moves=not args.no_moves, mutual_aid=args.mutual_aid)
    print(json.dumps(run(args.scenario, args.policy, args.seed, args.crews, flags), indent=1))


if __name__ == "__main__":
    main()
