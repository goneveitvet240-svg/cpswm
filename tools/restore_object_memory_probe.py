"""Fresh-process recovery and runtime-helper tamper probe for the saved owner run."""

import json
import sys
import time
from pathlib import Path

import torch
from run_correction_replay_comparison import OracleProducer
from surface_pipeline_fixture import SOURCE, restore_joint
from test_owned_rgbd_support import RGBDSupportDecoder

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.surface_episode import effective_surface_state


def run(root):
    torch.set_num_threads(2)
    started = time.perf_counter()
    config = json.loads((root / "restore.json").read_text())
    store = ContinuousStateStore(
        root / "copy.db", source_identity=SOURCE, dependency_identity=content_sha256(sys.version)
    )

    def unused(*a):
        raise AssertionError("must not re-run bootstrap")

    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=unused,
            joint_producer=restore_joint(config),
            observation_decoder=RGBDSupportDecoder(),
        )
        state = effective_surface_state(stream)
        expected = json.loads((root / "state-2.json").read_text())
        assert state == expected
        before = len(stream.observation_history())
        from cpswm.perception_mapping import external_object_sequence

        original = external_object_sequence.reference_fallback

        def forged(mapped, reference):
            return {"forged": True}

        external_object_sequence.reference_fallback = forged
        rejected = False
        try:
            stream.current_joint_decision_view()
        except ValueError as exc:
            rejected = True
            reason = str(exc)
        finally:
            external_object_sequence.reference_fallback = original
        assert rejected
        assert (
            effective_surface_state(stream) == expected
            and len(stream.observation_history()) == before
        )
        (root / "fresh.json").write_text(
            json.dumps(
                dict(
                    fresh_state_equal=True,
                    physical_journal_entries=before,
                    new_physical_dispatches=0,
                    runtime_helper_forgery_rejected=rejected,
                    reason=reason,
                    elapsed_s=time.perf_counter() - started,
                ),
                indent=2,
            )
        )
        print("fresh state identical; runtime helper forgery rejected", flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    run(Path(sys.argv[1]))
