"""Six deterministic integration fixtures, not a heldout scientific dataset."""

from __future__ import annotations

from dataclasses import dataclass, replace

from cpswm.simulation.contracts import Observation, Visibility

CONDITIONS = (
    "stable",
    "occluded_move",
    "identity_correction",
    "delayed_attribution",
    "habit_change",
    "execution_failure",
)


@dataclass(frozen=True)
class Scenario:
    episode_id: str
    condition: str
    history: tuple[Observation, ...]
    corrections: tuple[Observation, ...]
    initial_location: str
    expected_destination: str  # evaluator-only; never passed to the memory or executor
    fail_first: bool


def make_scenario(condition: str, seed: int = 7) -> Scenario:
    if condition not in CONDITIONS:
        raise ValueError("unknown condition")
    episode = f"integration-{condition}-{seed}"
    # Seeds are transport identities only here, NOT independent world replicates.
    positions = ["left", "left", "left", "right"]
    if condition in {"identity_correction", "delayed_attribution"}:
        positions = ["left", "right", "right"]
    if condition == "habit_change":
        positions = ["left", "right", "right", "right", "right"]
    history = []
    for tick, position in enumerate(positions):
        key = f"{episode}:historical:{tick}"
        history.append(
            Observation(
                episode,
                key,
                key,
                tick,
                tick,
                "target",
                Visibility.OBSERVED,
                position,
                (("owner", 1.0),),
            )
        )
    corrections = []
    if condition == "delayed_attribution":
        history = [
            history[0],
            *(replace(o, actors=(("owner", 0.7), ("guest", 0.3))) for o in history[1:]),
        ]
    if condition == "identity_correction":
        history = [history[0], *(replace(o, identity_probability=0.8) for o in history[1:])]
    if condition in {"identity_correction", "delayed_attribution"}:
        for offset, old in enumerate(history[1:]):
            corrections.append(
                replace(
                    old,
                    source_id=old.source_id + ":corrected",
                    revises=old.source_id,
                    available_at=10 + offset,
                    actors=(("guest", 1.0),) if condition == "delayed_attribution" else old.actors,
                    identity_probability=0.0 if condition == "identity_correction" else 1.0,
                )
            )
    if condition == "occluded_move":
        key = episode + ":lost"
        history.append(Observation(episode, key, key, 8, 8, "target", Visibility.LOST, None))
    return Scenario(
        episode,
        condition,
        tuple(history),
        tuple(corrections),
        "right" if condition == "occluded_move" else "center",
        "right" if condition == "habit_change" else "left",
        condition == "execution_failure",
    )
