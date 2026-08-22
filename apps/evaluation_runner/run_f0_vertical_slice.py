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
    parser.add_argument(
        "--allow-external-benchmark-dir",
        action="store_true",
        help=(
            "run against assets outside the repository's benchmarks/ tree. "
            "Those assets are NOT covered by source_tree_sha256, so the report's "
            "provenance no longer identifies the benchmark authority it used."
        ),
    )
    return parser.parse_args()


def resolve_benchmark_dir(benchmark_dir: Path, *, allow_external: bool) -> Path:
    """Reject assets the recorded provenance cannot bind.

    The checked-in manifest is the trusted benchmark authority only because it
    is covered by ``source_tree_sha256``.  Silently accepting an out-of-tree
    directory would make the report claim an authority it never read.
    """

    resolved = benchmark_dir.resolve()
    covered_root = (REPOSITORY_ROOT / "benchmarks").resolve()
    if allow_external or resolved.is_relative_to(covered_root):
        return resolved
    raise SystemExit(
        f"refusing to evaluate assets outside {covered_root}: {resolved}\n"
        "they are not covered by source_tree_sha256, so the report's provenance "
        "would not identify them. Pass --allow-external-benchmark-dir to override."
    )


def main() -> None:
    args = parse_args()
    benchmark_dir = resolve_benchmark_dir(
        args.benchmark_dir, allow_external=args.allow_external_benchmark_dir
    )
    manifest = BenchmarkManifest.model_validate_json(
        (benchmark_dir / "book_on_sofa_manifest_v0.4.json").read_text(encoding="utf-8")
    )
    routine_config = RoutineGenerationConfig.model_validate_json(
        (benchmark_dir / "book_on_sofa_routine_v0.2.json").read_text(encoding="utf-8")
    )
    policy = IncidentalObservationPolicy.model_validate_json(
        (benchmark_dir / "book_on_sofa_policy_v0.3.json").read_text(encoding="utf-8")
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
