"""Controlled legal/invalid/correct/restore source-to-command revision matrix."""

import argparse
import json
import subprocess
from dataclasses import replace
from pathlib import Path

from run_matched_value import save

from cpswm.simulation.contracts import Observation, Visibility
from cpswm.simulation.goal_control import GoalPlan, MemoryGoalController, fixture_observations
from cpswm.simulation.memory import SimulationMemory
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def run():
    rows = []
    for scenario in ("delayed_attribution", "identity_correction"):
        fixture = json.loads((ROOT / "configs/simulation/libero_goal_fixture.json").read_text())
        fixture["scenario"] = scenario
        history, corrections = fixture_observations(fixture)
        for arm in sorted(SimulationMemory.ARMS):
            controller = MemoryGoalController(
                fixture["episode_id"], fixture["catalogue"], arm, ROOT
            )
            for obs in history:
                controller.observe_history(obs, obs.available_at)
            visual = Observation(
                fixture["episode_id"],
                "visual:100",
                "visual:100",
                100,
                100,
                "target",
                Visibility.OBSERVED,
                "image_center",
                origin="sam2.1_tiny_operator_box",
            )
            controller.observe_visual(visual, 100)
            before = controller.audit()
            first = GoalPlan.from_payload(controller.plan(100)["plan"])
            assert first.command.destination == "stove"
            negative = []
            bad = [
                history[-1],
                replace(history[-1], source_id="disguised-duplicate"),
                replace(corrections[0], source_id="foreign", episode_id="foreign"),
                replace(corrections[0], source_id="missing-target", revises="missing"),
            ]
            for observation in bad:
                previous = content_sha256(controller.audit())
                try:
                    controller.observe_history(observation, 102)
                except ValueError as error:
                    negative.append(str(error))
                else:
                    raise AssertionError("invalid correction admitted")
                assert content_sha256(controller.audit()) == previous
                controller.validate(first)
            for obs in corrections:
                controller.observe_history(obs, 102)
            corrected = controller.audit()
            if arm == "ordinary_memory":
                controller.validate(first)
                second = first
            else:
                try:
                    controller.validate(first)
                except ValueError:
                    pass
                else:
                    raise AssertionError("stale plan accepted")
                second = GoalPlan.from_payload(controller.plan(102)["plan"])
                assert second.command.destination == "plate"
                assert second.goal_memory_revision != first.goal_memory_revision
                assert second.visual_source_id == first.visual_source_id
                assert second.prompt == fixture["catalogue"]["plate"]
            # Old source cannot overwrite a newer active source, even with fresh source id.
            stale = replace(corrections[0], source_id="stale-revision", available_at=103)
            previous = content_sha256(controller.audit())
            try:
                controller.observe_history(stale, 103)
            except ValueError:
                negative.append("stale active-source revision rejected")
            else:
                raise AssertionError("stale source revision admitted")
            assert content_sha256(controller.audit()) == previous
            for original, correction in zip(history[1:], corrections, strict=True):
                controller.observe_history(
                    replace(
                        original,
                        source_id=original.source_id + ":restored",
                        revises=correction.source_id,
                        available_at=103,
                    ),
                    103,
                )
            third = (
                first
                if arm == "ordinary_memory"
                else GoalPlan.from_payload(controller.plan(103)["plan"])
            )
            assert third.command.destination == "stove"
            if arm != "ordinary_memory":
                try:
                    controller.validate(second)
                except ValueError:
                    pass
                else:
                    raise AssertionError("restoration did not invalidate corrected command")
            runtime = controller.memory.runtime
            semantics = (
                []
                if runtime is None
                else [
                    {
                        "semantics": r.evidence_semantics,
                        "source_posterior": str(r.source_posterior_snapshot_id),
                        "independent_source": str(r.independent_observation_source_id),
                        "likelihood": r.observation_log_likelihood,
                    }
                    for batch in runtime.importance_revision_receipts
                    for r in batch
                ]
            )
            if runtime is not None:
                runtime.verify_internal_contracts()
                assert all(
                    r["semantics"] == "posterior_projection_not_likelihood"
                    and r["independent_source"] == "None"
                    and r["likelihood"] == 0
                    for r in semantics
                )
            rows.append(
                {
                    "scenario": scenario,
                    "arm": arm,
                    "before": before,
                    "corrected": corrected,
                    "restored": controller.audit(),
                    "plans": [first.payload(), second.payload(), third.payload()],
                    "invalid_cases_rejected_without_mutation": negative,
                    "evidence_semantics": semantics,
                    "corrected_goal_consumed_by_plan": second.command.destination == "plate",
                }
            )
    return {
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "rows": rows,
        "scientific_acceptance": False,
        "scope": "controlled semantic fixture; not natural visual attribution or global ORRER",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, run())
