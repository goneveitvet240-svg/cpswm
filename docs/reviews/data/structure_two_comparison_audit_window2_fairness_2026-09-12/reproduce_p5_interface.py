"""Window-three handoff: unchanged production consumer, first fixed opened D0 episode.

PYTHONPATH=src native-python this_file.py > NEW-output.json
This is an unverified descriptive interface probe, not a scientific certificate.
"""

import json
from pathlib import Path

from cpswm.contracts import ProjectTwoDatasetSplit as Split
from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit

root = Path(__file__).resolve().parents[4]
dataset = (
    audit.D0SyntheticReplayExperimentConfig.load(root / audit.DATA_CONFIG).build_adapter().build()
)
episode = dataset.visible_episodes(Split.TEST)[0]
state = audit.ReadoutCorrectedDirectP5LocationAdapter(episode)
schedule = audit.base._episode_schedule_commitment(episode)
rows = []
for index, step in enumerate(episode.steps):
    packet = audit.base._packet_for_step(episode, step, schedule_commitment_sha256=schedule)
    receipt = state.consume_matched_ciav_packet(packet, step, step_index=index)
    posterior = state.predict_location_posteriors(packet)
    raw = audit._p5_readouts(state)
    rows.append(
        {
            "step_id": str(step.step_id),
            "step_index": index,
            "transition_after": str(step.after.detected_location_id) if step.after else None,
            "ciav_detected": str(packet.realized_detected_location_id),
            "closure": receipt.closure_kind,
            "state_counts": raw["state_counts"],
            "habit": audit._distribution(posterior.owner_habit_location_distribution),
            "fast": raw["fast"],
            "surviving": raw["surviving"],
            "regime": raw["regime"],
        }
    )
print(
    json.dumps(
        {
            "development_only": True,
            "verification": "DESCRIPTIVE_INTERFACE_PROBE",
            "episode_id": str(episode.episode_id),
            "rows": rows,
        },
        indent=2,
    )
)
