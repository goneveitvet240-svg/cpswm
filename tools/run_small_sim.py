"""Run the opt-in CPSWM simulation integration framework (never real devices)."""

import argparse
from pathlib import Path

from cpswm.simulation.memory import SimulationMemory
from cpswm.simulation.runner import run_suite
from cpswm.simulation.scenarios import CONDITIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("event", "mujoco"), default="event")
    parser.add_argument("--arms", choices=sorted(SimulationMemory.ARMS), nargs="+")
    parser.add_argument("--conditions", choices=CONDITIONS, nargs="+")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    run_suite(args.output, args.backend, args.arms, args.conditions, args.seed, args.video)


if __name__ == "__main__":
    main()
