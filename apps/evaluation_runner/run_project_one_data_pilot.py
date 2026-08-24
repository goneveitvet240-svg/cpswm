"""Run the project-one fixed-parameter pilot over a real event log.

    PYTHONPATH=src python apps/evaluation_runner/run_project_one_data_pilot.py \
        --input /absolute/path/to/events.jsonl \
        --adapter jsonl \
        --output artifacts/project_one/real_data_pilot

With planted changes, so the run has change points to be scored against:

    PYTHONPATH=src python apps/evaluation_runner/run_project_one_data_pilot.py \
        --input /absolute/path/to/events.jsonl \
        --adapter jsonl \
        --inject one_shot_disturbance temporary_disturbance permanent_change \
                 recurring_regime \
        --output artifacts/project_one/semi_synthetic_pilot

Writes ``predictions.jsonl``, ``metrics.json``, ``paired.json`` and
``manifest.json``; with ``--inject``, also ``injections.json``.

No parameter selection happens here.  Every arm runs at the same fixed
thresholds, which is what makes the result a statement about the mechanism
rather than about how hard each arm was optimized.

Injection is applied **per binding**, not across the flat file: relocating
"the object" in a log containing several objects would move whichever one
happened to sit at that row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.project_one_data_pilot import (
    binding_stream,
    run_data_pilot,
    write_pilot_outputs,
)
from cpswm.system.evaluation_operations.project_one_household_generator import (
    build_household_log,
)
from cpswm.system.evaluation_operations.project_one_semi_synthetic import (
    InjectionKind,
    inject_changes,
)
from cpswm.system.evaluation_operations.project_one_stream_binding import (
    OPEN_SET_LOCATION,
    bind_stream,
)
from cpswm.system.evaluation_operations.real_data_adapters import (
    JSONLAdapter,
    UnknownLocationPolicy,
)

ADAPTERS = ("jsonl",)


def _build_adapter(arguments: argparse.Namespace) -> JSONLAdapter:
    if arguments.adapter != "jsonl":
        raise SystemExit(f"unsupported adapter {arguments.adapter!r}; available: {ADAPTERS}")
    return JSONLAdapter(
        arguments.input,
        truth_path=arguments.truth,
        unknown_location=UnknownLocationPolicy(arguments.unknown_location),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="event log to evaluate")
    parser.add_argument("--adapter", default="jsonl", choices=list(ADAPTERS))
    parser.add_argument(
        "--generated",
        action="store_true",
        help=(
            "build a multi-household synthetic log instead of reading --input; "
            "gives the pilot real entity scale with exact per-binding truth"
        ),
    )
    parser.add_argument("--households", type=int, default=3)
    parser.add_argument("--residents", type=int, default=2)
    parser.add_argument("--objects", type=int, default=4)
    parser.add_argument("--truth", type=Path, default=None, help="optional separate truth file")
    parser.add_argument(
        "--unknown-location",
        default=UnknownLocationPolicy.REJECT.value,
        choices=[item.value for item in UnknownLocationPolicy],
    )
    parser.add_argument(
        "--inject",
        nargs="*",
        default=[],
        choices=[item.value for item in InjectionKind],
        help="plant known changes so the run has change points to be scored against",
    )
    parser.add_argument("--seed", type=int, default=0, help="injection seed")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    declared_locations = None
    if arguments.generated:
        log = build_household_log(
            households=arguments.households,
            residents_per_household=arguments.residents,
            objects_per_resident=arguments.objects,
            seed=arguments.seed,
        )
        stream, truth = log.stream, log.truth
        # Declared rather than observed: a family that never moves would
        # otherwise present a one-member candidate set and drop out of the
        # denominator, which is the population most worth keeping.
        declared_locations = dict(log.candidate_locations)
        summary = log.manifest_summary()
        report_lines = [
            f"generated {summary['events']} event(s) across {summary['bindings']} binding(s), "
            f"{summary['households']} household(s), {summary['residents']} resident(s)"
        ]
    else:
        if arguments.input is None:
            raise SystemExit("either --input or --generated is required")
        adapter = _build_adapter(arguments)
        stream, truth = adapter.load(stream_id=adapter.discover_stream_id(), split="pilot")
        report_lines = [
            f"read {adapter.report.total_lines} line(s): "
            f"{adapter.report.accepted} accepted, "
            f"{adapter.report.duplicates_dropped} duplicate(s) dropped, "
            f"{len(adapter.report.malformed)} rejected"
        ]

    injections: list[dict[str, object]] = []
    not_injected: list[dict[str, object]] = []
    if arguments.inject:
        kinds = tuple(InjectionKind(name) for name in arguments.inject)
        streams = []
        for binding in bind_stream(stream, candidate_locations=declared_locations):
            if not binding.is_evaluable:
                continue
            sub_stream, sub_truth = binding_stream(binding, truth)
            try:
                pool = tuple(
                    name for name in binding.candidate_locations if name != OPEN_SET_LOCATION
                )
                planted = inject_changes(
                    sub_stream, sub_truth, kinds=kinds, seed=arguments.seed, location_pool=pool
                )
            except ValueError as error:
                # A real log mixes long and short histories.  A binding too
                # short to hold every requested plant is carried through
                # un-injected and reported, because dropping it would quietly
                # shrink the denominator, and aborting the whole run over one
                # short object would make --inject unusable on real data.
                not_injected.append({"binding_id": binding.binding_id, "reason": str(error)})
                streams.append((sub_stream, sub_truth))
                continue
            streams.append((planted.stream, planted.truth))
            injections.extend(
                {"binding_id": binding.binding_id, **item.as_dict()} for item in planted.injections
            )
        if not streams:
            raise SystemExit("no evaluable binding to inject into")
        report_lines.append(
            f"planted {len(injections)} change(s) across "
            f"{len(streams) - len(not_injected)} binding(s); "
            f"{len(not_injected)} binding(s) too short and left un-injected"
        )
        if not injections:
            raise SystemExit(
                "no binding was long enough for the requested injection kinds; "
                "request fewer kinds or supply longer histories"
            )
    else:
        streams = [(stream, truth)]

    report = run_data_pilot(streams=streams, candidate_locations=declared_locations)
    written = write_pilot_outputs(report, arguments.output)

    output: Path = arguments.output
    if not arguments.generated:
        (output / "adapter_report.json").write_text(
            json.dumps(adapter.report.as_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if injections or not_injected:
        (output / "injections.json").write_text(
            json.dumps(
                {"planted": injections, "not_injected": not_injected},
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    evaluable = [item for item in report.bindings if item.is_evaluable]
    for line in report_lines:
        print(line)
    print(f"bindings: {len(evaluable)} evaluated, {len(report.bindings) - len(evaluable)} skipped")
    print(f"arms={len(report.arms)} results={len(report.results)}")
    consistency = report.calibration_consistency
    print(
        f"as_is vs raw_clip: agree={consistency['agree']} "
        f"max_abs_difference={consistency['max_abs_difference']:.3e}"
    )
    print(f"predictions sha256 = {written['predictions_sha256']}")
    print(f"wrote {output}/predictions.jsonl, metrics.json, paired.json, manifest.json")

    if not consistency["agree"]:
        print(
            "WARNING: the two full-chain readings of the same RLS score disagree. "
            "The head is not emitting what the harness assumes; treat every number "
            "in this report as suspect until that is resolved."
        )
        return 1
    if report.failures():
        print(f"FAILURES: {len(report.failures())}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
