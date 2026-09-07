"""Runtime coverage for the global structure-two evidence-factor trace."""

from cpswm.contracts import EvidenceFactorOperator, ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_cross_swap_contamination import (
    selected_v06_readout,
)


def test_v06_runtime_emits_one_global_operator_trace_and_ciav_reuses_it():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(1201,),
        test_seeds=(6201,),
        max_steps_per_episode=12,
    ).build()
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)[0]
    state = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=selected_v06_readout(),
    )
    wrapper = _CIAVState(state, dataset, episode, enabled=False, cost_multiplier=1.0)
    assert wrapper.evidence_factor_trace is state.evidence_factor_trace

    for step in episode.steps:
        wrapper.observe(step)
        wrapper.predict()
        wrapper.feedback(step)

    operators = {item.operator for item in state.evidence_factor_trace.receipts}
    assert {
        EvidenceFactorOperator.OPCEU,
        EvidenceFactorOperator.PCHMP,
        EvidenceFactorOperator.CF_BOCPD,
        EvidenceFactorOperator.CCRR,
        EvidenceFactorOperator.RGRC,
        EvidenceFactorOperator.ACTION_READOUT,
        EvidenceFactorOperator.EXECUTION_FEEDBACK,
        EvidenceFactorOperator.ORRER_CHEH,
    } <= operators
    assert state.evidence_factor_trace.verify_chain()
