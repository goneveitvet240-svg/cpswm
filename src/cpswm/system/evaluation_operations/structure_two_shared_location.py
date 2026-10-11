"""Shared empirical location predictions and reversible, source-bound history.

These are search-head statistics, not native particle or owner-habit writes.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from cpswm.system.evaluation_operations.structure_two_current_location import (
    CurrentLocationActionState,
    CurrentLocationBelief,
    LocationModelConfig,
)
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class SharedLocationConfig(LocationModelConfig):
    sharing: float = 0.0
    persistence: float = 0.0

    def __post_init__(self):
        super().__post_init__()
        if any(not math.isfinite(v) or v < 0 for v in (self.sharing, self.persistence)):
            raise ValueError("sharing and persistence must be finite nonnegative mass")
        if self.kind == "recent" and (self.sharing or self.persistence):
            raise ValueError("recent control has no statistical augmentation")


class SharedLocationBelief(CurrentLocationBelief):
    def __init__(self, locations, actors, config):
        super().__init__(locations, actors, config)
        self._sources = {}
        self._raw_history = []
        self._withdrawn = set()
        self.revision_receipts = []

    def table(self):
        table = super().table()
        pooled = {
            actor: {
                loc: sum(table[previous, actor, loc] for previous in (None, *self.locations))
                for loc in self.locations
            }
            for actor in self.actors
        }
        global_location = {loc: sum(row[loc] for row in pooled.values()) for loc in self.locations}
        for previous in (None, *self.locations):
            for actor in self.actors:
                distribution = global_location if self.config.kind == "markov" else pooled[actor]
                total = sum(distribution.values())
                for loc in self.locations:
                    table[previous, actor, loc] += (
                        self.config.sharing / len(self.actors) * distribution[loc] / total
                    )
                    if previous == loc:
                        table[previous, actor, loc] += self.config.persistence / len(self.actors)
        return table

    def finish(self):
        super().finish()
        row = self.records[-1]
        # Copy at the ownership boundary; returned logs cannot rewrite sources.
        source = copy.deepcopy(
            {"input": row["input"], "updates": row["updates"], "found": row["found"]}
        )
        step_id = row["input"]["step_id"]
        self._sources[step_id] = (source, content_sha256(source))
        self._raw_history.append(copy.deepcopy(self.history[-1]))

    def source_digest(self, step_id):
        if step_id not in self._sources:
            raise ValueError("unknown location evidence source")
        return self._sources[step_id][1]

    def revise_location_source(self, step_id, expected_digest, *, restore=False):
        """Rebuild the causal suffix; preserve elapsed slots and original actions."""
        if self.pending is not None:
            raise ValueError("cannot revise history during an unfinished search")
        if type(restore) is not bool or step_id not in self._sources:
            raise ValueError("invalid location-source revision")
        source, digest = self._sources[step_id]
        if expected_digest != digest or content_sha256(source) != digest:
            raise ValueError("location revision has wrong or mutated source binding")
        if restore != (step_id in self._withdrawn):
            raise ValueError("location source is already in requested state")
        withdrawn = set(self._withdrawn)
        if restore:
            withdrawn.remove(step_id)
        else:
            withdrawn.add(step_id)
        history, previous = [], None
        for raw in self._raw_history:
            record = copy.deepcopy(raw)
            record["previous"] = previous
            if raw["step_id"] in withdrawn:
                # No observation at this tick. Carry prior trusted position;
                # unlike a genuine full negative sweep, do not clear it.
                record["found"] = None
            else:
                previous = record["found"]
            history.append(record)
        receipt = {
            "operation": "restore" if restore else "withdraw",
            "step_id": step_id,
            "source_sha256": digest,
            "before_history_sha256": content_sha256(self.history),
            "after_history_sha256": content_sha256(history),
            "before_previous": self.previous,
            "after_previous": previous,
            "history_slots": len(history),
            "previous_revision_sha256": self.revision_receipts[-1]["receipt_sha256"]
            if self.revision_receipts
            else None,
        }
        receipt["receipt_sha256"] = content_sha256(receipt)
        self._withdrawn, self.history, self.previous = withdrawn, history, previous
        # No current search is active. A subsequent begin rebuilds its belief;
        # do not leave a stale posterior looking like a revised current belief.
        self.joint, self.checked = {}, []
        self.found, self.exhausted = None, False
        self.revision_receipts.append(receipt)
        return copy.deepcopy(receipt)


class AuditedCurrentLocationActionState(CurrentLocationActionState):
    """Inspect event-time readiness; never multiply a new factor into stale state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.native_time_audits = []

    def observe(self, step):
        super().observe(step)
        result = self.state.step_results.get(step.step_id)
        last = self.state.runtime._last_observation
        current = (
            result is not None
            and last is not None
            and last.source_update_id == result.event_revision_id
        )
        has_location = step.after is not None and step.after.detected_location_id is not None
        status = (
            "current_position_already_consumed"
            if current and has_location
            else "no_native_event_state"
            if last is None
            else "no_current_event_binding"
        )
        self.native_time_audits.append(
            {
                "step_id": str(step.step_id),
                "current_transition_exists": result is not None,
                "native_source_update_id": None if last is None else str(last.source_update_id),
                "current_transition_revision_id": None
                if result is None
                else str(result.event_revision_id),
                "native_binds_current_transition": current,
                "original_location_visible": has_location,
                "status": status,
                "location_factor_applied_to_native": False,
            }
        )
