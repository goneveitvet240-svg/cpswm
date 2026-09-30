"""Owned public surface readouts and a separate private seed/reference join.

No private data can enter public_readout. The driver owns externally pinned
lineage, the fixed original checkpoint and all 96 frames including empty ones.
"""

from __future__ import annotations

import copy
from collections import Counter

from instance_affinity_dataset import VOID_PRIORITY, _recheck_public, label_frame
from offline_frontend_evaluation import _xyz

from cpswm.data_preflight.soft_surface_position import readout_frame
from cpswm.system.reproducibility import content_sha256

REFERENCES = ("sdk_transform_position_m", "sdk_aabb_center_m")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def public_readout(record, affinity_model, affinity_pin):
    """Rebuild from owned RGB-D and public candidates; no private label arguments."""
    fresh = _recheck_public(record)
    metadata = fresh["public_metadata"]
    return readout_frame(
        fresh["rgb"],
        fresh["depth"],
        fresh["camera"],
        [{key: row[key] for key in ("method", "id", "box")} for row in fresh["candidates"]],
        affinity_model,
        affinity_pin,
        provenance=dict(
            source_sha256=content_sha256(metadata),
            receipt_sha256=metadata["receipt_sha256"],
            observation_ids=metadata["observation_ids"],
            payload_sha256=metadata["payload_sha256"],
        ),
    )


def label_readout(
    record,
    readout,
    sdk,
    info,
    masks,
    segmentation,
    eligibility,
    *,
    affinity_model,
    affinity_pin,
    sdk_rgb_bytes,
    sdk_depth_bytes,
):
    """Attach both SDK references only to unique eligible rendered seed members.

    All SDK instances, invisible entries, unavailable seeds and VOID rows stay.
    Single-pixel neighborhoods use direct masks even though no pair exists.
    The public readout is rederived before the strict original pair join validates
    same-event bytes/camera, complete catalog/masks and final eligibility audit.
    """
    fresh = public_readout(record, affinity_model, affinity_pin)
    _require(content_sha256(readout) == content_sha256(fresh), "public readout differs")
    _require(type(eligibility) is list and eligibility, "nonempty complete eligibility required")
    verified = label_frame(
        record,
        sdk,
        info,
        masks,
        segmentation,
        eligibility,
        sdk_rgb_bytes=sdk_rgb_bytes,
        sdk_depth_bytes=sdk_depth_bytes,
    )
    instances = verified["instances"]
    audits = {row["object_id"]: row["eligibility"] for row in instances}
    groups = {(row["house_index"], row["split"]) for row in audits.values()}
    _require(len(groups) == 1, "private eligibility must name exactly one house/split")
    house_index, split = next(iter(groups))
    objects = {row["objectId"]: row for row in sdk["metadata"]["objects"]}
    pixels = sorted({tuple(row["pixel_uv"]) for row in fresh["seeds"]})
    point_members = []
    lookup = {}
    for u, v in pixels:
        members = sorted(row["object_id"] for row in instances if masks[row["array_key"]][v, u])
        point = dict(
            pixel_uv=[u, v],
            object_ids=members,
            eligible_object_ids=[identity for identity in members if audits[identity]["eligible"]],
        )
        lookup[(u, v)] = point
        point_members.append(point)
    seeds = {row["seed_id"]: row for row in fresh["seeds"]}
    labels, reasons = [], Counter({reason: 0 for reason in VOID_PRIORITY})
    for observation in fresh["observations"]:
        seed = seeds[observation["seed_id"]]
        point = lookup[tuple(seed["pixel_uv"])]
        if not seed["valid"]:
            reason = "invalid_depth"
        elif len(point["object_ids"]) > 1:
            reason = "ambiguous_membership"
        elif not point["object_ids"]:
            reason = "unmapped_pixel"
        elif not point["eligible_object_ids"]:
            reason = "ineligible_instance"
        else:
            reason = None
        object_id = point["object_ids"][0] if reason is None else None
        targets = dict.fromkeys(REFERENCES)
        if object_id is not None:
            obj = objects[object_id]
            targets = dict(
                zip(
                    REFERENCES,
                    (
                        list(_xyz(obj["position"])),
                        list(_xyz(obj["axisAlignedBoundingBox"]["center"])),
                    ),
                    strict=True,
                )
            )
        else:
            reasons[reason] += 1
        labels.append(
            dict(
                measurement_id=observation["measurement_id"],
                seed_id=seed["seed_id"],
                estimator=observation["estimator"],
                eligible=reason is None,
                void_reason=reason,
                object_id=object_id,
                targets=targets,
                pixel_uv=seed["pixel_uv"],
                house_index=house_index,
                split=split,
            )
        )
    _require(
        sum(reasons.values()) == sum(not row["eligible"] for row in labels),
        "seed VOID accounting differs",
    )
    return dict(
        schema="private-soft-surface-seed-supervision@1",
        action_id=record["action_id"],
        input_sha256=fresh["input_sha256"],
        readout_sha256=content_sha256(fresh),
        house_index=house_index,
        split=split,
        labels=labels,
        point_members=point_members,
        instances=copy.deepcopy(instances),
        void_counts=dict(reasons),
        void_reason_priority=list(VOID_PRIORITY),
        void_count_unit="estimator_observation",
        seed_void_counts={reason: count // 2 for reason, count in reasons.items()},
        references=list(REFERENCES),
        supervision="unique-eligible-rendered-seed-membership-not-depth-ownership",
        formal_position_reference_selected=False,
        private_lineage_sha256=content_sha256(dict(sdk=sdk, info=info, eligibility=eligibility)),
    )
