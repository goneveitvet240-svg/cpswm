"""RQ1: one contract binding opportunity, propensity, occlusion and missingness.

The audit line:

    RQ1 长期选择性观察 -- 路线正确 -- 接入前缺口: 统一机会, 倾向, 遮挡, 缺失机制契约.

Three of the four already exist and are good.  :class:`ObservationOpportunityRecord`
carries the sensing opportunity and its selection probability;
:class:`ObservationDetectionResult` carries the outcome and refuses to fill
identity from truth on a miss; :class:`ObservationPropensityCorrector` turns a
propensity into an auditable weight.  They are, however, three separate objects
that meet only inside :meth:`HierarchicalDirichletHabitModel.update_from_opportunity`,
and the fourth — the **missingness mechanism** — exists nowhere except a
docstring sentence saying *"missingness is usually MNAR"*.

That last omission is the load-bearing one, and it is not a bookkeeping
complaint.  Inverse-propensity weighting is unbiased under MAR *given the
covariates actually recorded*.  Under MNAR it is not, and applying it produces
a number that looks corrected and is not.  Today nothing in the type system
distinguishes:

* a run whose propensity model conditions on everything that drove the looking
  (correction is justified), from
* a run where the robot looked because it already suspected the object had
  moved (correction is biased, and biased *toward* the effect being measured).

Both produce the same ``PropensityWeight``.  A reader cannot tell them apart,
and neither can a future maintainer.

:class:`ObservationMechanismEnvelope` is the single record that makes the four
travel together and makes the mechanism a declared, validated field rather than
an assumption:

* ``MAR`` requires a non-empty ``conditioning_covariates``.  You cannot claim
  "missing at random given the covariates" without naming them.
* ``MNAR`` permits a correction but forces
  :attr:`CorrectionValidity.BIASED_DECLARED` and requires a
  ``residual_bias_note``, so the bias is written down next to the number.
* ``UNDECLARED`` — the honest default — forbids any correction other than 1.0.
  Silence is not MAR.

`项目结构一 §7`'s four prohibitions are enforced here too, because each of them
is a statement about the observation mechanism rather than about the model:

    not_observed 不等于不存在
    未打开容器不能产生容器内部负证据
    低质量视角不能产生强排除
    纯模型预测不能成为新的训练证据

The first and last are already structural in
:class:`ObservationDetectionResult` and :class:`HabitLearningEvidence`.  The
middle two are not, and become so here: full occlusion and a low-quality view
cannot carry negative evidence, whatever the outcome field says.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isclose, isfinite
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .base import (
    BaseRecordMetadata,
    ContractModel,
    EvidenceRef,
    Probability,
    require_aware,
)
from .habit_learning import (
    HabitLearningEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
)

__all__ = [
    "OBSERVATION_MECHANISM_VERSION",
    "STRONG_EXCLUSION_QUALITY_FLOOR",
    "CorrectionValidity",
    "MissingnessMechanism",
    "ObservationMechanismEnvelope",
    "PropensityRecord",
    "validate_habit_update_binding",
]

OBSERVATION_MECHANISM_VERSION = "observation-mechanism@0.1"

#: Field-of-view coverage below which a view is too poor to exclude anything.
#: `§7`: 低质量视角不能产生强排除.  A declared constant rather than a magic
#: number at a call site, because it is a claim about sensing, not a tuning knob.
STRONG_EXCLUSION_QUALITY_FLOOR = 0.5

StrictlyPositiveProbability = Annotated[float, Field(gt=0.0, le=1.0)]


class MissingnessMechanism(StrEnum):
    """Why an observation is missing.  Determines whether IPW means anything."""

    #: Missing completely at random: looking is independent of the state.
    #: Rare in a task-driven robot and should be justified when claimed.
    MCAR = "mcar"
    #: Missing at random *given the recorded covariates*.  IPW is unbiased.
    MAR = "mar"
    #: Missing not at random: the decision to look depends on the unobserved
    #: state.  IPW is biased; the bias must be declared, not corrected away.
    MNAR = "mnar"
    #: Nothing has been established.  The honest default, and the one that
    #: forbids correction.
    UNDECLARED = "undeclared"


class CorrectionValidity(StrEnum):
    """What the applied propensity weight is worth."""

    #: No correction applied; the count is the raw count.
    UNCORRECTED = "uncorrected"
    #: Correction applied under a mechanism that justifies it.
    UNBIASED_UNDER_DECLARED_MECHANISM = "unbiased_under_declared_mechanism"
    #: Correction applied under MNAR.  Residual bias remains, and is declared.
    BIASED_DECLARED = "biased_declared"


class PropensityRecord(ContractModel):
    """The applied correction, kept beside the mechanism that justifies it."""

    mode: str = Field(min_length=1)
    raw_propensity: StrictlyPositiveProbability
    applied_weight: float = Field(gt=0.0)
    clipped: bool = False
    minimum_propensity: StrictlyPositiveProbability | None = None

    @model_validator(mode="after")
    def validate_weight(self) -> PropensityRecord:
        if not isfinite(self.applied_weight):
            raise ValueError("applied_weight must be finite")
        if self.clipped and self.minimum_propensity is None:
            raise ValueError("a clipped weight must record the clip threshold it hit")
        if (
            self.minimum_propensity is not None
            and self.clipped
            and self.raw_propensity > self.minimum_propensity
        ):
            raise ValueError("a weight cannot be clipped above its own threshold")
        return self

    @property
    def is_corrected(self) -> bool:
        return not isclose(self.applied_weight, 1.0, rel_tol=0.0, abs_tol=1e-12)


class ObservationMechanismEnvelope(ContractModel):
    """Opportunity, outcome, propensity and missingness mechanism, as one record.

    The envelope is what a habit update should cite.  Citing the opportunity
    alone loses the mechanism; citing the weight alone loses the reason the
    weight is allowed to exist.
    """

    metadata: BaseRecordMetadata
    opportunity: ObservationOpportunityRecord
    detection: ObservationDetectionResult | None = None
    missingness_mechanism: MissingnessMechanism = MissingnessMechanism.UNDECLARED
    #: What ``MAR`` is conditional on.  Names of covariates the propensity
    #: model actually used -- task, route, room, time of day, prior belief.
    conditioning_covariates: tuple[str, ...] = ()
    propensity: PropensityRecord | None = None
    residual_bias_note: str = ""
    envelope_version: str = OBSERVATION_MECHANISM_VERSION
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("conditioning_covariates")
    @classmethod
    def validate_covariates(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("conditioning covariate names must be non-empty")
        if len(set(value)) != len(value):
            raise ValueError("conditioning covariates must be unique")
        return value

    @model_validator(mode="after")
    def validate_envelope(self) -> ObservationMechanismEnvelope:
        self._validate_binding()
        self._validate_mechanism()
        self._validate_negative_evidence()
        return self

    # -- binding -------------------------------------------------------------

    def _validate_binding(self) -> None:
        detection = self.detection
        if detection is None:
            return
        if detection.observation_opportunity_id != self.opportunity.metadata.record_id:
            raise ValueError("detection result does not cite this opportunity")
        for name in ("household_id", "session_id", "trace_id"):
            if getattr(detection.metadata, name) != getattr(self.opportunity.metadata, name):
                raise ValueError(f"detection {name} does not match the opportunity")
        if detection.outcome == ObservationOutcome.DETECTED and not self.opportunity.selected:
            raise ValueError("an unselected opportunity cannot produce a detection")

    # -- mechanism -----------------------------------------------------------

    def _validate_mechanism(self) -> None:
        mechanism = self.missingness_mechanism
        propensity = self.propensity
        corrected = propensity is not None and propensity.is_corrected

        if mechanism is MissingnessMechanism.MAR and not self.conditioning_covariates:
            raise ValueError(
                "MAR must name the covariates it is conditional on; "
                "'missing at random' without them is an assertion, not a model"
            )
        if mechanism is MissingnessMechanism.MCAR and self.conditioning_covariates:
            raise ValueError(
                "MCAR conditions on nothing by definition; "
                "declare MAR if the propensity model uses covariates"
            )
        if mechanism is MissingnessMechanism.UNDECLARED and corrected:
            raise ValueError(
                "an undeclared missingness mechanism cannot justify a propensity "
                "correction; silence is not MAR"
            )
        if mechanism is MissingnessMechanism.MNAR and corrected and not self.residual_bias_note:
            raise ValueError("an MNAR correction must record the residual bias it does not remove")
        if mechanism is not MissingnessMechanism.MNAR and self.residual_bias_note:
            raise ValueError("residual_bias_note is only meaningful under MNAR")

    # -- §7's two unenforced prohibitions ------------------------------------

    def _validate_negative_evidence(self) -> None:
        detection = self.detection
        if detection is None or detection.negative_evidence_strength <= 0.0:
            return
        context = self.opportunity.incidental_context
        if context is not None:
            if context.occlusion_state is OcclusionState.FULL:
                raise ValueError(
                    "a fully occluded view cannot produce negative evidence "
                    "(§7: 未打开容器不能产生容器内部负证据)"
                )
            if context.occlusion_state is OcclusionState.UNKNOWN:
                raise ValueError(
                    "negative evidence requires a known occlusion state; "
                    "unknown occlusion cannot exclude anything"
                )
            if context.field_of_view_coverage < STRONG_EXCLUSION_QUALITY_FLOOR:
                raise ValueError(
                    "a low-quality view cannot produce a strong exclusion "
                    "(§7: 低质量视角不能产生强排除)"
                )
        if self.opportunity.p_detect_given_state_action <= 0.0:
            raise ValueError(
                "an opportunity that could never have detected the object "
                "cannot produce negative evidence"
            )

    # -- derived -------------------------------------------------------------

    @property
    def correction_validity(self) -> CorrectionValidity:
        """What the applied weight is worth, derived rather than asserted."""

        if self.propensity is None or not self.propensity.is_corrected:
            return CorrectionValidity.UNCORRECTED
        if self.missingness_mechanism is MissingnessMechanism.MNAR:
            return CorrectionValidity.BIASED_DECLARED
        return CorrectionValidity.UNBIASED_UNDER_DECLARED_MECHANISM

    @property
    def supports_habit_update(self) -> bool:
        """Whether this envelope may back a long-term habit update at all."""

        detection = self.detection
        return (
            self.opportunity.selected
            and detection is not None
            and detection.outcome == ObservationOutcome.DETECTED
        )

    @property
    def observation_time(self) -> datetime:
        detection = self.detection
        if detection is not None and detection.detection_time is not None:
            return detection.detection_time
        return self.opportunity.opportunity_time

    @property
    def occlusion_state(self) -> OcclusionState:
        context = self.opportunity.incidental_context
        return OcclusionState.UNKNOWN if context is None else context.occlusion_state

    @property
    def effective_weight(self) -> float:
        return 1.0 if self.propensity is None else self.propensity.applied_weight

    def audit_payload(self) -> dict[str, object]:
        """Everything a reader needs to judge one corrected count."""

        return {
            "envelope_version": self.envelope_version,
            "opportunity_id": str(self.opportunity.metadata.record_id),
            "selected": self.opportunity.selected,
            "outcome": None if self.detection is None else self.detection.outcome.value,
            "occlusion_state": self.occlusion_state.value,
            "missingness_mechanism": self.missingness_mechanism.value,
            "conditioning_covariates": list(self.conditioning_covariates),
            "propensity_mode": None if self.propensity is None else self.propensity.mode,
            "raw_propensity": (
                None if self.propensity is None else repr(self.propensity.raw_propensity)
            ),
            "effective_weight": repr(self.effective_weight),
            "correction_validity": self.correction_validity.value,
            "residual_bias_note": self.residual_bias_note,
            "supports_habit_update": self.supports_habit_update,
        }


def validate_habit_update_binding(
    evidence: HabitLearningEvidence,
    envelope: ObservationMechanismEnvelope,
) -> None:
    """Refuse a habit update whose observation mechanism does not back it.

    The three refusals, in the order they matter:

    1. The update must cite *this* opportunity.  An update citing a different
       one has been corrected by a weight computed for a different look.
    2. The envelope must actually be a detection.  `§7`: ``not_observed`` is
       not evidence of anything, so it cannot produce a count.
    3. A corrected weight requires a declared mechanism.  This is the check
       that had no home before, and the reason the envelope exists.
    """

    if evidence.observation_opportunity_id is None:
        raise ValueError("a mechanism-bound habit update must cite its opportunity")
    if evidence.observation_opportunity_id != envelope.opportunity.metadata.record_id:
        raise ValueError("habit evidence cites a different observation opportunity")
    for name in ("household_id", "session_id", "trace_id"):
        if getattr(evidence.metadata, name) != getattr(envelope.opportunity.metadata, name):
            raise ValueError(f"habit evidence {name} does not match the observation opportunity")
    if not envelope.supports_habit_update:
        raise ValueError(
            "only a selected opportunity that produced a detection may back a habit update"
        )
    if (
        envelope.propensity is not None
        and envelope.propensity.is_corrected
        and envelope.missingness_mechanism is MissingnessMechanism.UNDECLARED
    ):
        raise ValueError("a corrected habit update requires a declared missingness mechanism")
    detection = envelope.detection
    assert detection is not None  # guaranteed by supports_habit_update
    if (
        detection.detected_object_instance_id is not None
        and detection.detected_object_instance_id != evidence.object_instance_id
    ):
        raise ValueError("habit evidence object does not match the detected object")
    if (
        detection.detected_location_id is not None
        and detection.detected_location_id != evidence.location_id
    ):
        raise ValueError("habit evidence location does not match the detected location")
    if detection.detection_time is not None:
        require_aware(detection.detection_time, "detection_time")
        if evidence.event_time != detection.detection_time:
            raise ValueError("habit evidence event_time does not match the detection time")


def _probability(value: float, name: str) -> Probability:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a probability")
    return value
