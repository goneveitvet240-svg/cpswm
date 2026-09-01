"""World-distributed Structure-Two D0 generator v0.2.

Unlike the legacy day-index fixture, this generator separates three sources of
variation:

* ``world_seed`` samples a household and its latent habit distributions;
* ``trajectory_seed`` samples one latent behaviour/event trajectory;
* ``observation_seed`` samples MNAR visibility and perception noise only.

The module is method-free.  It exposes rich evaluator truth for Gate A, but it
does not adapt the rollouts to any Structure-Two method until the frozen target
gate passes.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Any

from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-generator@0.2"
CONTEXTS = ("weekday", "weekend")
REGIMES = ("baseline", "shifted", "recurrent")


@dataclass(frozen=True, slots=True)
class RangeSpec:
    low: float
    high: float

    def sample(self, rng: random.Random) -> float:
        return float(rng.uniform(self.low, self.high))


@dataclass(frozen=True, slots=True)
class IntegerRangeSpec:
    low: int
    high: int

    def sample(self, rng: random.Random) -> int:
        return int(rng.randint(self.low, self.high))


@dataclass(frozen=True, slots=True)
class WorldDistributionConfig:
    duration_days: IntegerRangeSpec
    location_count: IntegerRangeSpec
    guest_actor_count: IntegerRangeSpec
    abrupt_fraction: RangeSpec
    recurrence_fraction: RangeSpec
    owner_event_probability: RangeSpec
    unknown_event_probability: RangeSpec
    habit_mode_mass: RangeSpec
    habit_secondary_mass: RangeSpec
    weekend_distinct_mode_probability: float
    base_observation_probability: RangeSpec
    location_visibility_multiplier: RangeSpec
    guest_visibility_multiplier: float
    unknown_visibility_multiplier: float
    weekend_visibility_multiplier: float
    actor_map_accuracy: RangeSpec
    identity_match_accuracy: RangeSpec
    handoff_probability: RangeSpec

    @classmethod
    def from_manifest(cls, payload: dict[str, Any]) -> WorldDistributionConfig:
        def floating(name: str) -> RangeSpec:
            low, high = payload[name]
            return RangeSpec(float(low), float(high))

        def integer(name: str) -> IntegerRangeSpec:
            low, high = payload[name]
            return IntegerRangeSpec(int(low), int(high))

        return cls(
            duration_days=integer("duration_days_inclusive"),
            location_count=integer("location_count_inclusive"),
            guest_actor_count=integer("guest_actor_count_inclusive"),
            abrupt_fraction=floating("abrupt_fraction"),
            recurrence_fraction=floating("recurrence_fraction"),
            owner_event_probability=floating("owner_event_probability"),
            unknown_event_probability=floating("unknown_event_probability"),
            habit_mode_mass=floating("habit_mode_mass"),
            habit_secondary_mass=floating("habit_secondary_mass"),
            weekend_distinct_mode_probability=float(payload["weekend_distinct_mode_probability"]),
            base_observation_probability=floating("base_observation_probability"),
            location_visibility_multiplier=floating("location_visibility_multiplier"),
            guest_visibility_multiplier=float(payload["guest_visibility_multiplier"]),
            unknown_visibility_multiplier=float(payload["unknown_visibility_multiplier"]),
            weekend_visibility_multiplier=float(payload["weekend_visibility_multiplier"]),
            actor_map_accuracy=floating("actor_map_accuracy"),
            identity_match_accuracy=floating("identity_match_accuracy"),
            handoff_probability=floating("handoff_probability"),
        )


@dataclass(frozen=True, slots=True)
class StructureTwoWorld:
    world_seed: int
    duration_days: int
    locations: tuple[str, ...]
    owner_actor: str
    guest_actors: tuple[str, ...]
    abrupt_day: int
    recurrence_day: int
    owner_event_probability: float
    unknown_event_probability: float
    actor_map_accuracy: float
    identity_match_accuracy: float
    handoff_probability: float
    base_observation_probability: float
    location_visibility: dict[str, float]
    habit_distributions: dict[str, dict[str, float]]
    guest_distributions: dict[str, dict[str, float]]
    world_hash: str

    def habit_distribution(self, regime: str, context: str) -> dict[str, float]:
        return self.habit_distributions[f"{regime}:{context}"]


@dataclass(frozen=True, slots=True)
class StructureTwoWorldStep:
    day: int
    context: str
    regime: str
    true_actor: str
    true_location: str
    true_owner_habit_location: str
    true_habit_distribution: dict[str, float]
    true_mechanism: str
    true_cause: str
    true_identity_match: bool
    event_chain: tuple[str, ...]
    observed: bool
    observation_propensity: float
    observed_location: str | None
    visible_actor_map: str | None
    visible_owner_probability: float | None
    visible_identity_confidence: float | None


@dataclass(frozen=True, slots=True)
class StructureTwoWorldRollout:
    world_seed: int
    trajectory_seed: int
    observation_seed: int
    world_hash: str
    rollout_id: str
    owner_actor: str
    locations: tuple[str, ...]
    steps: tuple[StructureTwoWorldStep, ...]


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in values.values())
    if total <= 0.0:
        return {key: 1.0 / len(values) for key in values}
    return {key: max(0.0, value) / total for key, value in values.items()}


def _mode(distribution: dict[str, float]) -> str:
    return min(distribution.items(), key=lambda item: (-item[1], item[0]))[0]


def _draw(rng: random.Random, distribution: dict[str, float]) -> str:
    keys = sorted(distribution)
    return str(rng.choices(keys, weights=[distribution[key] for key in keys], k=1)[0])


class StructureTwoWorldGeneratorV02:
    """Sample worlds and nested rollouts from one frozen distribution."""

    def __init__(self, config: WorldDistributionConfig) -> None:
        self.config = config

    def sample_world(self, world_seed: int) -> StructureTwoWorld:
        rng = random.Random(f"{PROTOCOL_ID}:world:{world_seed}")
        duration = self.config.duration_days.sample(rng)
        location_count = self.config.location_count.sample(rng)
        guest_count = self.config.guest_actor_count.sample(rng)
        locations = tuple(
            f"location-{content_sha256(f'{PROTOCOL_ID}:world:{world_seed}:loc:{index}')[:16]}"
            for index in range(location_count)
        )
        owner = "owner"
        guests = tuple(f"guest_{index + 1}" for index in range(guest_count))
        abrupt = max(14, round(duration * self.config.abrupt_fraction.sample(rng)))
        recurrence = min(
            duration - 14,
            round(duration * self.config.recurrence_fraction.sample(rng)),
        )
        if recurrence <= abrupt + 14:
            recurrence = abrupt + 15

        owner_probability = self.config.owner_event_probability.sample(rng)
        unknown_probability = min(
            self.config.unknown_event_probability.sample(rng),
            0.95 - owner_probability,
        )
        mode_mass = self.config.habit_mode_mass.sample(rng)
        secondary_mass = min(
            self.config.habit_secondary_mass.sample(rng),
            mode_mass - 0.05,
        )

        available = list(locations)
        baseline_mode = rng.choice(available)
        shifted_mode = rng.choice([item for item in available if item != baseline_mode])
        weekday_modes = {"baseline": baseline_mode, "shifted": shifted_mode}
        weekend_modes: dict[str, str] = {}
        for regime, weekday_mode in weekday_modes.items():
            alternatives = [item for item in available if item != weekday_mode]
            weekend_modes[regime] = (
                rng.choice(alternatives)
                if rng.random() < self.config.weekend_distinct_mode_probability
                else weekday_mode
            )

        habit_distributions: dict[str, dict[str, float]] = {}
        for regime in ("baseline", "shifted"):
            for context, mode_location in (
                ("weekday", weekday_modes[regime]),
                ("weekend", weekend_modes[regime]),
            ):
                secondary = rng.choice([item for item in available if item != mode_location])
                residual = (1.0 - mode_mass - secondary_mass) / (location_count - 2)
                habit_distributions[f"{regime}:{context}"] = _normalize(
                    {
                        item: (
                            mode_mass
                            if item == mode_location
                            else secondary_mass
                            if item == secondary
                            else residual
                        )
                        for item in available
                    }
                )
        for context in CONTEXTS:
            habit_distributions[f"recurrent:{context}"] = dict(
                habit_distributions[f"baseline:{context}"]
            )

        guest_distributions: dict[str, dict[str, float]] = {}
        owner_modes = {
            _mode(habit_distributions[f"{regime}:{context}"])
            for regime in REGIMES
            for context in CONTEXTS
        }
        for guest in guests:
            preferred = rng.choice(
                [item for item in available if item not in owner_modes] or available
            )
            secondary = rng.choice([item for item in available if item != preferred])
            residual = 0.15 / (location_count - 2)
            guest_distributions[guest] = _normalize(
                {
                    item: 0.65 if item == preferred else 0.20 if item == secondary else residual
                    for item in available
                }
            )

        location_visibility = {
            item: self.config.location_visibility_multiplier.sample(rng) for item in available
        }
        actor_map_accuracy = self.config.actor_map_accuracy.sample(rng)
        identity_match_accuracy = self.config.identity_match_accuracy.sample(rng)
        handoff_probability = self.config.handoff_probability.sample(rng)
        base_observation_probability = self.config.base_observation_probability.sample(rng)
        unhashed: dict[str, Any] = {
            "duration_days": duration,
            "location_count": location_count,
            "guest_count": guest_count,
            "abrupt_day": abrupt,
            "recurrence_day": recurrence,
            "owner_event_probability": owner_probability,
            "unknown_event_probability": unknown_probability,
            "actor_map_accuracy": actor_map_accuracy,
            "identity_match_accuracy": identity_match_accuracy,
            "handoff_probability": handoff_probability,
            "base_observation_probability": base_observation_probability,
            "location_visibility": location_visibility,
            "habit_distributions": habit_distributions,
            "guest_distributions": guest_distributions,
        }
        world_hash = content_sha256(unhashed)
        return StructureTwoWorld(
            world_seed=world_seed,
            duration_days=duration,
            locations=locations,
            owner_actor=owner,
            guest_actors=guests,
            abrupt_day=abrupt,
            recurrence_day=recurrence,
            owner_event_probability=owner_probability,
            unknown_event_probability=unknown_probability,
            actor_map_accuracy=actor_map_accuracy,
            identity_match_accuracy=identity_match_accuracy,
            handoff_probability=handoff_probability,
            base_observation_probability=base_observation_probability,
            location_visibility=location_visibility,
            habit_distributions=habit_distributions,
            guest_distributions=guest_distributions,
            world_hash=world_hash,
        )

    def generate_rollout(
        self,
        world: StructureTwoWorld,
        *,
        trajectory_seed: int,
        observation_seed: int,
    ) -> StructureTwoWorldRollout:
        trajectory_rng = random.Random(
            f"{PROTOCOL_ID}:trajectory:{world.world_seed}:{trajectory_seed}"
        )
        observation_rng = random.Random(
            f"{PROTOCOL_ID}:observation:{world.world_seed}:{trajectory_seed}:{observation_seed}"
        )
        actors = (world.owner_actor, *world.guest_actors, "unknown_actor")
        steps: list[StructureTwoWorldStep] = []
        for day in range(world.duration_days):
            context = "weekday" if day % 7 < 5 else "weekend"
            regime = (
                "baseline"
                if day < world.abrupt_day
                else "shifted"
                if day < world.recurrence_day
                else "recurrent"
            )
            habit = world.habit_distribution(regime, context)
            owner_mode = _mode(habit)
            actor_draw = trajectory_rng.random()
            if actor_draw < world.unknown_event_probability:
                actor = "unknown_actor"
            elif actor_draw < world.unknown_event_probability + world.owner_event_probability:
                actor = world.owner_actor
            else:
                actor = str(trajectory_rng.choice(world.guest_actors))

            if actor == world.owner_actor:
                location = _draw(trajectory_rng, habit)
                cause = "owner_habit_sample"
            elif actor == "unknown_actor":
                location = str(trajectory_rng.choice(world.locations))
                cause = "open_world_hidden_event"
            else:
                location = _draw(trajectory_rng, world.guest_distributions[actor])
                cause = "guest_relocation"
            mechanism = (
                "unknown"
                if actor == "unknown_actor"
                else "handoff"
                if actor != world.owner_actor
                and trajectory_rng.random() < world.handoff_probability
                else "direct"
            )

            propensity = world.base_observation_probability * world.location_visibility[location]
            if actor == "unknown_actor":
                propensity *= self.config.unknown_visibility_multiplier
            elif actor != world.owner_actor:
                propensity *= self.config.guest_visibility_multiplier
            if context == "weekend":
                propensity *= self.config.weekend_visibility_multiplier
            propensity = max(0.05, min(0.98, propensity))
            observed = observation_rng.random() < propensity
            observed_location: str | None = None
            actor_map: str | None = None
            owner_probability: float | None = None
            identity_confidence: float | None = None
            identity_match = True
            if observed:
                identity_match = observation_rng.random() < world.identity_match_accuracy
                observed_location = (
                    location
                    if identity_match
                    else str(
                        observation_rng.choice(
                            [item for item in world.locations if item != location]
                        )
                    )
                )
                actor_correct = observation_rng.random() < world.actor_map_accuracy
                actor_map = (
                    actor
                    if actor_correct
                    else str(observation_rng.choice([item for item in actors if item != actor]))
                )
                owner_probability = (
                    0.78
                    if actor_map == world.owner_actor
                    else 0.12
                    if actor == world.owner_actor
                    else 0.08
                )
                identity_confidence = 0.88 if identity_match else 0.32

            steps.append(
                StructureTwoWorldStep(
                    day=day,
                    context=context,
                    regime=regime,
                    true_actor=actor,
                    true_location=location,
                    true_owner_habit_location=owner_mode,
                    true_habit_distribution=dict(habit),
                    true_mechanism=mechanism,
                    true_cause=cause,
                    true_identity_match=True,
                    event_chain=("pick_up", "carry", "place"),
                    observed=observed,
                    observation_propensity=propensity,
                    observed_location=observed_location,
                    visible_actor_map=actor_map,
                    visible_owner_probability=owner_probability,
                    visible_identity_confidence=identity_confidence,
                )
            )
        rollout_id = content_sha256(
            {
                "world_hash": world.world_hash,
                "trajectory_seed": trajectory_seed,
                "observation_seed": observation_seed,
            }
        )
        return StructureTwoWorldRollout(
            world_seed=world.world_seed,
            trajectory_seed=trajectory_seed,
            observation_seed=observation_seed,
            world_hash=world.world_hash,
            rollout_id=rollout_id,
            owner_actor=world.owner_actor,
            locations=world.locations,
            steps=tuple(steps),
        )


def world_payload(world: StructureTwoWorld) -> dict[str, Any]:
    return asdict(world)


__all__ = [
    "CONTEXTS",
    "PROTOCOL_ID",
    "REGIMES",
    "StructureTwoWorld",
    "StructureTwoWorldGeneratorV02",
    "StructureTwoWorldRollout",
    "StructureTwoWorldStep",
    "WorldDistributionConfig",
    "world_payload",
]
