"""Paid native withdrawal/restoration continuations, engineering evidence only."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_current_event import build, dataset_for, plain
from verify_full_mechanism_value import save

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


def probe():
    data = dataset_for("sparse32", [66001])
    ep = data.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    cases = []
    for arm in FullJointArm:
        result = {"arm": arm.value, "branches": {}}
        for mode in ("control", "withdraw", "restore"):
            state = build(data, ep, arm.value)
            for step in ep.steps[:6]:
                state.observe(step)
                state.predict()
                state.feedback(step)
            runtime = state.runtime
            source_id = next(iter(runtime.location_sources))
            source = runtime.location_sources[source_id]
            before = runtime._state_sha256()
            ledger = runtime.rgrc_ledger.head_hash
            if mode != "control":
                runtime.revise_location_source(source_id, source["sha256"])
            if mode == "restore":
                runtime.revise_location_source(source_id, source["sha256"], restore=True)
            after = runtime._state_sha256()
            if mode == "restore":
                assert before == after and runtime.rgrc_ledger.head_hash == ledger
            step = ep.steps[6]
            state.observe(step)
            state.predict()
            state.feedback(step)
            result["branches"][mode] = {
                "before": before,
                "after_revision": after,
                "next_action": state.event_actions[-1],
                "revision_receipts": runtime.location_revisions,
                "final_state": runtime._state_sha256(),
                "native_steps": runtime.step_index,
            }
        assert (
            result["branches"]["control"]["next_action"]
            == result["branches"]["restore"]["next_action"]
        )
        assert (
            result["branches"]["control"]["final_state"]
            == result["branches"]["restore"]["final_state"]
        )
        cases.append(result)
    return {
        "cases": cases,
        "actual_step_executions": 42,
        "scope": (
            "two native arms, three independently executed seven-step prefixes; "
            "development engineering only"
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    save(a.output, plain(probe()))
    print("native revision continuations passed")
