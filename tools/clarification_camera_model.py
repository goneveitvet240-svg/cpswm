"""User-approved development objective: clarify hypotheses, never declare found.

Exact log-score decisions implement one-step full-hypothesis information value.
The original likelihoods, cost and camera choices remain explicitly uncalibrated.
This is not a new formal task metric or evidence of recognizing a target instance.
"""

from math import fsum, log2

from run_neural_pixel_camera_loop import ASSUMPTIONS, SOURCES, DiagnosticViewModel

from cpswm.system.evaluation_operations.structure_two_selected_method import TypedParticleState
from cpswm.system.joint_camera_policy import CameraAlternative, JointCameraProblem
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_continuous_input import ObservationDelivery

CLARIFICATION_SOURCES = SOURCES.model_copy(
    update={
        "utility_definition_id": "full-hypothesis-log-score-clarification-development@1",
        "utility_artifact_sha256": content_sha256(
            dict(
                objective="expected full-hypothesis Shannon uncertainty reduction in bits",
                unresolved_is_task_success=False,
                time_cost=ASSUMPTIONS["time_cost"],
                repeated_static_view="no new information within the current native generation",
            )
        ),
    }
)


class ClarificationViewModel(DiagnosticViewModel):
    sources = CLARIFICATION_SOURCES

    def problem(self, view, visible_prefix, *, decision_time, execution_history=()):
        base = super().problem(
            view, visible_prefix, decision_time=decision_time, execution_history=execution_history
        )
        prior = view.verification_belief().as_uuid_prior()
        heading = ASSUMPTIONS["initial_heading"]
        outcomes = {}
        # All actual rotations locate the camera. Only the current semantic
        # snapshot AND full atom support authorize reusable measurement beliefs.
        for command, delivery in sorted(
            ((c, d) for c, d in execution_history if type(d) is ObservationDelivery),
            key=lambda row: (row[1].received_at, str(row[0].action_id)),
        ):
            if not delivery.success:
                continue
            if command.action == "RotateLeft":
                heading = (heading - command.degrees) % 360
            if command.action == "RotateRight":
                heading = (heading + command.degrees) % 360
            if command.snapshot_id != view.snapshot_id or not command.reason.startswith(
                "joint-ciav@1:"
            ):
                continue
            problem = JointCameraProblem.model_validate_json(
                command.reason.removeprefix("joint-ciav@1:")
            )
            support = set(
                next(iter(problem.alternatives[0].candidate.outcome_likelihoods.values()))
            )
            if support == set(prior) and problem.model_sources == self.sources:
                outcome = self.decoder.decode(delivery.observations, cutoff=delivery.received_at)
                if outcome is not None:
                    if outcome not in {"category_candidate", "no_category_candidate"}:
                        raise ValueError("undeclared clarification measurement outcome")
                    outcomes[heading] = outcome
        atom_headings = {
            a.particle_id: ASSUMPTIONS["unknown_instance_hypothesis_view"]
            if TypedParticleState.model_validate_json(a.state_json).instance_association_key
            == "unknown_instance"
            else ASSUMPTIONS["known_instance_hypothesis_view"]
            for a in view.atoms
        }
        options = []
        distributions = [prior]
        for target, option in zip((225.0, 315.0), base.alternatives, strict=True):
            if target in outcomes:
                likelihood = dict.fromkeys(prior, float(outcomes[target] == "category_candidate"))
            else:
                likelihood = {
                    key: ASSUMPTIONS["aggregate_unresolved_candidate_probability"]
                    if key == view.unresolved_id
                    else ASSUMPTIONS["candidate_probability_at_hypothesis_view"]
                    if atom_headings[key] == target
                    else ASSUMPTIONS["candidate_probability_elsewhere"]
                    for key in prior
                }
            candidate = option.candidate.model_copy(
                update={
                    "outcome_likelihoods": {
                        "category_candidate": likelihood,
                        "no_category_candidate": {
                            key: 1 - value for key, value in likelihood.items()
                        },
                    }
                }
            )
            options.append(
                CameraAlternative(candidate=candidate, action=option.action, degrees=option.degrees)
            )
            for values in candidate.outcome_likelihoods.values():
                total = fsum(prior[key] * values[key] for key in prior)
                if total > 0:
                    distributions.append({key: prior[key] * values[key] / total for key in prior})
        # The prior and all reachable posteriors are sufficient terminal reports
        # for the proper log score. Zero-prior atoms remain impossible under these
        # fixed likelihoods; their finite utility has zero expected contribution.
        utilities = {
            content_uuid("clarification-report", (view.content_sha256, index)): {
                key: log2(value) if value > 0 else 0.0 for key, value in q.items()
            }
            for index, q in enumerate(distributions)
        }
        return base.model_copy(
            update={
                "model_sources": self.sources,
                "alternatives": tuple(options),
                "terminal_decision_utilities": utilities,
            }
        )
