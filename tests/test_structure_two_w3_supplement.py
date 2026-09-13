"""Small final action-effect checks, independent of the aggregate pass counts."""

import pytest
import test_structure_two_formal_revision_lineage as legacy
from structure_two_backbone_wiring_probe import CalibratedRetractionPolicy
from test_structure_two_w3_revision_acceptance import correction


def test_public_correction_replaces_the_decoded_action_and_old_mass():
    probe = legacy._legacy_history(1)
    core = probe.system.core
    journal = legacy._journal(probe)
    original = next(iter(core._committed_events))
    old_location = core._committed_events[original].location_id
    before = probe.action_distribution()
    assert before[old_location] == 1.0
    corrected, _, _ = correction(probe, original, same=False, mass=1.0)
    new_location = core._committed_events[corrected].location_id
    after = probe.action_distribution()
    assert after[old_location] == 0.0
    assert after[new_location] == 1.0
    assert legacy._decoded_action(probe) == new_location
    assert core.hybrid_alpha(old_location) == 0.0
    assert not core._hybrid_loop.ledger.live_promoted_records_for_revision(original)
    legacy._assert_reconciled_against_journal(probe, journal)


@pytest.mark.parametrize("path", ["caller_policy", "multi_axis"])
@pytest.mark.parametrize("stage", ["hybrid", "dirichlet", "rls"])
def test_feedback_interruption_restores_all_state_and_allows_retry(path, stage, monkeypatch):
    probe = legacy._legacy_history(1)
    core = probe.system.core
    target = next(iter(core._committed_events))
    bundle = legacy._feedback(probe, target)
    before = legacy._full_state(probe)
    qualifications = dict(core._write_eligibility)

    def run():
        if path == "caller_policy":
            return legacy._apply(
                probe,
                bundle,
                policy=CalibratedRetractionPolicy(
                    corrected_location_id=core._committed_events[target].location_id,
                    corrected_owner_mass=0.25,
                ),
            )
        feedback, binding, likelihood = bundle
        return probe.system.process_project_two_feedback(
            history=core._event_histories[target],
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
        )

    def interrupt(_self, current_stage):
        if current_stage == stage:
            raise KeyboardInterrupt("revision interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(type(core), "_revision_fault_hook", interrupt)
        with pytest.raises(KeyboardInterrupt, match="revision interrupted"):
            run()
    assert legacy._full_state(probe) == before
    assert core._write_eligibility == qualifications
    assert not core.revision_transactions
    assert not probe.system.feedback_revision_loop._projector._seen
    run()
    assert target not in core._committed_events
    assert len(core.revision_transactions) == 1
