"""Opt-in empirical current-location head, separate from owner-habit authority.

Only whitelisted current cues and previously paid terminal positions enter this
model. Its actor-location belief is a search submodel, not the native H/R/I/C/Z
particle posterior. Soft cue counts are empirical labels, not actor ground truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from cpswm.system.evaluation_operations.structure_two_active_location_search import (
    LocationInspectionRequest,
)
from cpswm.system.evaluation_operations.structure_two_executed_search import receipt_payload
from cpswm.system.reproducibility import content_sha256, content_uuid


def normalize(values):
    total = sum(values.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("belief requires finite positive mass")
    if any(not math.isfinite(v) or v < 0 for v in values.values()):
        raise ValueError("belief has invalid mass")
    return {k: v / total for k, v in values.items()}


@dataclass(frozen=True)
class LocationModelConfig:
    kind: str
    alpha: float = 1.0
    decay: float = 1.0

    def __post_init__(self):
        if self.kind not in {"recent", "markov", "joint", "factor"}:
            raise ValueError("unknown current-location model")
        if not math.isfinite(self.alpha) or self.alpha <= 0:
            raise ValueError("alpha must be positive")
        if not math.isfinite(self.decay) or not 0 < self.decay <= 1:
            raise ValueError("decay must lie in (0, 1]")


def project_search_input(step, actors, *, view):
    """No UUID-derived features, dates, mechanisms or hidden labels are exposed."""
    if view not in {"native", "cue_only"}:
        raise ValueError("unknown projection view")
    location = None
    if view == "native" and step.after is not None:
        location = step.after.detected_location_id
    cue = None
    if step.actor_evidence is not None:
        raw = step.actor_evidence.actor_posterior
        if set(raw) - set(actors):
            raise ValueError("cue actor is outside public support")
        cue = normalize({a: float(raw.get(a, 0.0)) for a in actors})
    return {
        "step_id": str(step.step_id),
        "object_id": str(step.object_instance_id),
        "view": view,
        "visible_location": None if location is None else str(location),
        "actor_cue": cue,
    }


class CurrentLocationBelief:
    """Online soft transition counts, ideal-detector conditioning, causal carry."""

    def __init__(self, locations, actors, config):
        self.locations = tuple(sorted(map(str, locations)))
        self.actors = tuple(sorted(actors))
        if (
            not self.locations
            or len(set(self.locations)) != len(self.locations)
            or not self.actors
            or len(set(self.actors)) != len(self.actors)
        ):
            raise ValueError("model supports must be nonempty and unique")
        self.config = config
        self.history = []
        self.previous = None
        self.pending = None
        self.joint = {}
        self.checked = []
        self.found = None
        self.exhausted = False
        self.records = []

    def table(self):
        # alpha is the total pseudocount for each previous-location row.
        prior = self.config.alpha / (len(self.actors) * len(self.locations))
        table = {
            (previous, actor, location): prior
            for previous in (None, *self.locations)
            for actor in self.actors
            for location in self.locations
        }
        for index, row in enumerate(self.history):
            if row["found"] is None:
                continue
            weight = self.config.decay ** (len(self.history) - index - 1)
            cue = row["actor_cue"] or dict.fromkeys(self.actors, 1 / len(self.actors))
            for actor in self.actors:
                table[row["previous"], actor, row["found"]] += weight * cue[actor]
        return table

    def begin(self, projection):
        if self.pending is not None:
            raise ValueError("previous search is unfinished")
        if set(projection) != {"step_id", "object_id", "view", "visible_location", "actor_cue"}:
            raise ValueError("search input violates whitelist")
        if any(row["step_id"] == projection["step_id"] for row in self.history):
            raise ValueError("search step was already learned")
        if projection["visible_location"] not in (None, *self.locations):
            raise ValueError("visible position is outside support")
        cue = projection["actor_cue"]
        if cue is not None:
            if set(cue) != set(self.actors) or abs(sum(cue.values()) - 1) > 1e-9:
                raise ValueError("actor cue has invalid support or normalization")
            normalize(cue)
        table = self.table()
        row_location = {
            loc: sum(table[self.previous, a, loc] for a in self.actors) for loc in self.locations
        }
        actor_location = {
            (a, loc): sum(table[p, a, loc] for p in (None, *self.locations))
            for a in self.actors
            for loc in self.locations
        }
        location_total = {
            loc: sum(actor_location[a, loc] for a in self.actors) for loc in self.locations
        }
        kind = self.config.kind
        if kind == "joint":
            raw = {
                (a, loc): table[self.previous, a, loc]
                for a in self.actors
                for loc in self.locations
            }
        elif kind == "factor":
            raw = {
                (a, loc): row_location[loc] * actor_location[a, loc] / location_total[loc]
                for a in self.actors
                for loc in self.locations
            }
        else:
            raw = {
                (a, loc): (1.0 if kind == "recent" else row_location[loc]) / len(self.actors)
                for a in self.actors
                for loc in self.locations
            }
        joint = normalize(raw)
        if cue is not None and kind in {"joint", "factor"}:
            # The input is already a public actor posterior, not a likelihood.
            # Replace its marginal once; never multiply it twice by a prior.
            actor_mass = {a: sum(joint[a, loc] for loc in self.locations) for a in self.actors}
            joint = {(a, loc): cue[a] * joint[a, loc] / actor_mass[a] for a, loc in joint}
        visible = projection["visible_location"]
        if visible is not None:
            joint = normalize(
                {(a, loc): v if loc == visible else 0.0 for (a, loc), v in joint.items()}
            )
        self.pending = {**projection, "actor_cue": None if cue is None else dict(cue)}
        self.joint = joint
        self.checked = []
        self.found = None
        self.exhausted = False
        prior = self.export_joint()
        self.records.append(
            {
                "input": self.pending,
                "input_sha256": content_sha256(self.pending),
                "history_before_sha256": content_sha256(self.history),
                "previous": self.previous,
                "prior_joint": prior,
                "prior_location": self.location_distribution(),
                "planned_order": self.rank(),
                "updates": [],
            }
        )

    def export_joint(self):
        return {
            a: {loc: self.joint.get((a, loc), 0.0) for loc in self.locations} for a in self.actors
        }

    def location_distribution(self):
        return {
            loc: sum(self.joint.get((a, loc), 0.0) for a in self.actors) for loc in self.locations
        }

    def rank(self):
        marginal = self.location_distribution()
        first = None
        if self.config.kind == "recent":
            first = self.pending["visible_location"] or self.previous
        return sorted(
            self.locations, key=lambda loc: (loc != first, -round(marginal[loc], 14), loc)
        )

    def consume(self, request, receipt, environment):
        if self.pending is None or self.found is not None or self.exhausted:
            raise ValueError("no unfinished belief to condition")
        environment.validate_receipt(request, receipt)
        location = str(request.location_id)
        if (
            str(request.step_id) != self.pending["step_id"]
            or str(request.object_id) != self.pending["object_id"]
            or location not in self.locations
            or location in self.checked
            or receipt.ordinal != len(self.checked) + 1
        ):
            raise ValueError("location observation has wrong binding or sequence")
        updated = {
            (a, loc): v if (loc == location) == receipt.found else 0.0
            for (a, loc), v in self.joint.items()
        }
        checked = [*self.checked, location]
        exhausted = not receipt.found and len(checked) == len(self.locations)
        if sum(updated.values()) <= 0 and not exhausted:
            raise ValueError("detector contradicts current visible position")
        self.joint = updated if exhausted else normalize(updated)
        self.checked = checked
        self.found = location if receipt.found else None
        self.exhausted = exhausted
        self.records[-1]["updates"].append(
            {"receipt": receipt_payload(receipt), "posterior_joint": self.export_joint()}
        )

    def finish(self):
        if self.pending is None or (self.found is None and not self.exhausted):
            raise ValueError("terminal evidence is required before learning")
        self.history.append(
            {
                "step_id": self.pending["step_id"],
                "previous": self.previous,
                "actor_cue": self.pending["actor_cue"],
                "found": self.found,
            }
        )
        self.previous = self.found
        self.records[-1].update(
            found=self.found,
            status="found" if self.found is not None else "support_exhausted",
            paid_checks=len(self.checked),
            history_after_sha256=content_sha256(self.history),
        )
        self.pending = None


def execute_current_search(head, projection, environment):
    """Select and charge each location before consuming its detector result."""
    head.begin(projection)
    environment.begin_step(UUID(projection["step_id"]))
    environment.finish_probing()
    while head.found is None and not head.exhausted:
        location = next(loc for loc in head.rank() if loc not in head.checked)
        request = LocationInspectionRequest(
            content_uuid(
                "current-location-inspect",
                (environment.episode_id, projection["step_id"], location),
            ),
            environment.episode_id,
            UUID(projection["step_id"]),
            UUID(projection["object_id"]),
            UUID(location),
        )
        receipt = environment.inspect(request)
        head.consume(request, receipt, environment)
    environment.close()
    head.finish()
    return head.records[-1]


class CurrentLocationActionState:
    """Opt-in full-framework adapter. Search head never receives native answers."""

    def __init__(self, state, environment, head, *, view):
        self.state, self.environment, self.head, self.view = state, environment, head, view
        self._step = None
        self._pending_feedback = False

    def observe(self, step):
        if self._pending_feedback:
            raise ValueError("framework feedback must precede the next step")
        self.state.observe(step)
        self._step = step

    def predict(self):
        from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction

        if self._step is None or self._pending_feedback:
            raise ValueError("prediction requires one fresh observed step")
        native = self.state.predict()
        snapshot = self.state.spine.current_snapshot.snapshot_id
        committed = dict(self.state.spine._committed_events)
        projection = project_search_input(self._step, self.head.actors, view=self.view)
        row = execute_current_search(self.head, projection, self.environment)
        prediction = _Prediction(
            native.put_back, tuple(map(UUID, row["planned_order"])), native.unknown_probability
        )
        self.state.bind_prediction_trace(prediction, self.state._prediction_index - 1)
        if (
            snapshot != self.state.spine.current_snapshot.snapshot_id
            or committed != self.state.spine._committed_events
        ):
            raise AssertionError("search head acquired habit write authority")
        self._pending_feedback = True
        return prediction

    def feedback(self, step):
        if not self._pending_feedback or step.step_id != self._step.step_id:
            raise ValueError("framework feedback has no completed search")
        self.state.feedback(step)
        self._pending_feedback = False

    def __getattr__(self, name):
        return getattr(self.state, name)
