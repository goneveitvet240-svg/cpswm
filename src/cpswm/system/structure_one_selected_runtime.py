"""Composition root for the user-selected Structure One method stack."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cpswm.system.structure_one_ingress import (
    StructureOneBackend,
    StructureOneCertifiedIngress,
    StructureOneModule,
)
from cpswm.system.structure_one_learning_backends import (
    ConstrainedLLMQueryCompiler,
    OfflineToControlledOnlinePolicyPlanner,
    RLSOnlyCFBOCPDHabitBackend,
)
from cpswm.system.structure_one_runtime import (
    CommonsenseProvider,
    HiddenEventBackend,
    ObjectIdentityBackend,
    StructureOneQueryEngine,
    StructureOneRuntime,
)
from cpswm.system.structure_one_selected_routes import (
    SELECTED_STRUCTURE_ONE_METHODS,
    StructureOneMethodSelection,
)


@dataclass(frozen=True, slots=True)
class SelectedStructureOneSystem:
    selection: StructureOneMethodSelection
    selection_signature: str
    runtime: StructureOneRuntime


def build_selected_structure_one_system(
    *,
    identity_backend: ObjectIdentityBackend,
    commonsense_provider: CommonsenseProvider,
    hidden_event_backend: HiddenEventBackend,
    habit_backend: RLSOnlyCFBOCPDHabitBackend,
    query_compiler: ConstrainedLLMQueryCompiler,
    query_engine: StructureOneQueryEngine,
    policy_planner: OfflineToControlledOnlinePolicyPlanner,
    belief_state_backend: StructureOneBackend,
    hidden_event_ledger_backend: StructureOneBackend,
    additional_backends: Mapping[StructureOneModule, StructureOneBackend] | None = None,
) -> SelectedStructureOneSystem:
    """Bind the selected methods without exposing an uncertified write path."""

    backends = dict(additional_backends or {})
    mandatory: dict[StructureOneModule, StructureOneBackend] = {
        StructureOneModule.HABIT_LEDGER: habit_backend,
        StructureOneModule.BELIEF_STATE: belief_state_backend,
        StructureOneModule.HIDDEN_EVENT_LEDGER: hidden_event_ledger_backend,
    }
    overlap = set(backends).intersection(mandatory)
    if overlap:
        names = ", ".join(sorted(module.value for module in overlap))
        raise ValueError(f"additional_backends cannot replace selected backends: {names}")
    backends.update(mandatory)
    ingress = StructureOneCertifiedIngress(backends=backends)
    runtime = StructureOneRuntime(
        ingress=ingress,
        query_compiler=query_compiler,
        identity_backend=identity_backend,
        commonsense_provider=commonsense_provider,
        hidden_event_backend=hidden_event_backend,
        query_engine=query_engine,
        assistance_planner=policy_planner,
    )
    selection = SELECTED_STRUCTURE_ONE_METHODS
    return SelectedStructureOneSystem(
        selection=selection,
        selection_signature=selection.signature(),
        runtime=runtime,
    )
