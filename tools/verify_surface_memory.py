"""Fresh owner replay and reversible static lookup controls, no new observations.

This tests subsequent lookup of the same recorded epoch. It never extrapolates a
remembered point to a changed world or claims novel-task generalization.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from uuid import UUID

import torch
from run_correction_replay_comparison import OracleProducer
from run_surface_episode import reports, save
from surface_pipeline_fixture import SOURCE, restore_joint
from test_owned_rgbd_support import RGBDSupportDecoder

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.surface_episode import effective_surface_state


def resume(db, config):
    store = ContinuousStateStore(
        db, source_identity=SOURCE, dependency_identity=content_sha256(sys.version)
    )

    def unused(*args):
        raise AssertionError("memory restore cannot rerun bootstrap")

    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=unused,
            joint_producer=restore_joint(config),
            observation_decoder=RGBDSupportDecoder(),
        )
    except BaseException:
        store.close()
        raise
    return store, stream


def run(root, output):
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads((root / "restore.json").read_text())
    original = json.loads((root / "result.json").read_text())
    expected = original["final_reports"]
    for phase in ("retain", "withdraw-first", "withdraw-last", "reset"):
        folder = output / phase
        folder.mkdir()
        db = folder / "state.db"
        with sqlite3.connect(root / "copy.db") as source, sqlite3.connect(db) as target:
            source.backup(target)
        store, stream = resume(db, config)
        try:
            before = reports(stream, config["queries"], config["reference_action"])
            if before != expected:
                raise ValueError("fresh-process original reports differ")
            physical_before = stream.observation_history()
            effective = effective_surface_state(stream)["action_ids"]
            selected = []
            if phase == "withdraw-first":
                selected = effective[:1]
            elif phase == "withdraw-last":
                selected = effective[-1:]
            elif phase == "reset":
                selected = list(reversed(effective))
            for key in selected:
                stream.withdraw_owned_position_observation(
                    UUID(key), reason="static lookup control: " + phase
                )
            after = reports(stream, config["queries"], config["reference_action"])
            if stream.observation_history() != physical_before:
                raise ValueError("withdrawal changed acquisition history")
            if phase in ("withdraw-first", "reset") and any(
                r["status"] != "unknown" for r in after
            ):
                raise ValueError("withdrawn reference silently rebound")
            save(
                folder / "control.json",
                dict(
                    phase=phase,
                    before=before,
                    after=after,
                    config=config,
                    database=str(db),
                    withdrawn=selected,
                    physical_dispatches=len(physical_before),
                    later_task_actions=0,
                    effective_actions=effective_surface_state(stream)["action_ids"],
                    scope="static lookup at recorded epoch; not changed-world current location",
                ),
            )
        finally:
            store.close()
        print(json.dumps(dict(phase=phase, statuses=[r["status"] for r in after])), flush=True)


def verify(folder):
    record = json.loads((folder / "control.json").read_text())
    store, stream = resume(folder / "state.db", record["config"])
    try:
        cfg = record["config"]
        value = reports(stream, cfg["queries"], cfg["reference_action"])
        if value != record["after"]:
            raise ValueError("withdrawn-state fresh replay differs")
        if len(stream.observation_history()) != record["physical_dispatches"]:
            raise ValueError("fresh physical journal differs")
        if effective_surface_state(stream)["action_ids"] != record["effective_actions"]:
            raise ValueError("fresh effective memory differs")
        save(
            folder / "fresh-verification.json",
            dict(equal=True, physical_actions_preserved=True, no_external_executor=True),
        )
    finally:
        store.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("run", "verify"))
    p.add_argument("root", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    torch.set_num_threads(2)
    if a.mode == "run":
        if a.output is None:
            p.error("run requires --output")
        run(a.root, a.output)
    else:
        verify(a.root)
