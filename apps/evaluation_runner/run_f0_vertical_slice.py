"""Run the checked-in OAM-PHM F0 book-on-sofa benchmark slice."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cpswm.system.evaluation_operations import EvaluationRunner  # noqa: E402
from cpswm.system.household_memory_benchmark import (  # noqa: E402
    BenchmarkManifest,
    EvaluationTrack,
)
from cpswm.system.synthetic_routines import (  # noqa: E402
    RoutineGenerationConfig,
    SyntheticRoutineGenerator,
)
from cpswm.system.world_model_simulator import (  # noqa: E402
    IncidentalObservationPolicy,
    SymbolicWorldModelSimulator,
)
from cpswm.system.world_model_simulator.benchmark_access import (  # noqa: E402
    issue_benchmark_ground_truth_capability,
)


DEFAULT_BENCHMARK_DIR = REPOSITORY_ROOT / "benchmarks" / "oam_phm_f0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the reproducible OAM-PHM F0 book-on-sofa slice."
    )
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=DEFAULT_BENCHMARK_DIR,
        help="directory containing the versioned manifest, routine, and policy JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = args.benchmark_dir.resolve()
    manifest = BenchmarkManifest.model_validate_json(
        (benchmark_dir / "book_on_sofa_manifest_v0.4.json").read_text(
            encoding="utf-8"
        )
    )
    routine_config = RoutineGenerationConfig.model_validate_json(
        (benchmark_dir / "book_on_sofa_routine_v0.2.json").read_text(
            encoding="utf-8"
        )
    )
    policy = IncidentalObservationPolicy.model_validate_json(
        (benchmark_dir / "book_on_sofa_policy_v0.3.json").read_text(
            encoding="utf-8"
        )
    )

    plan = SyntheticRoutineGenerator().generate(routine_config)
    simulation = SymbolicWorldModelSimulator().run_privileged(
        plan,
        policy,
        capability=issue_benchmark_ground_truth_capability(),
    )
    report = EvaluationRunner().evaluate(
        manifest,
        simulation,
        track=EvaluationTrack.CONTROLLED_NOISE,
    )
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
