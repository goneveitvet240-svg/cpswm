"""Conservative deterministic M21 query-compiler baseline.

The compiler performs no world-model write and invents no entity.  It either
binds an utterance to a caller-provided lexicon or explicitly abstains.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.contracts.base import EvidenceRef
from cpswm.contracts.grounded_search import CompiledSemanticQuery
from cpswm.contracts.llm_roles import build_query_compiler_provenance


@dataclass(frozen=True, slots=True)
class QueryLexiconEntry:
    canonical_category: str
    aliases: tuple[str, ...]
    attributes: tuple[str, ...] = ()
    person_entity_ids: tuple[UUID, ...] = ()


class DeterministicM21QueryCompiler:
    """Auditable M21 baseline; a learned/LLM compiler remains a method choice."""

    VERSION = "deterministic-m21-v1"

    def __init__(self, *, lexicon: tuple[QueryLexiconEntry, ...]) -> None:
        self._lexicon = lexicon

    def compile(
        self,
        utterance: str,
        *,
        input_evidence_refs: tuple[EvidenceRef, ...] = (),
    ) -> CompiledSemanticQuery:
        if not input_evidence_refs:
            source_record_id = uuid5(NAMESPACE_URL, f"cpswm:m21:utterance:{utterance}")
            input_evidence_refs = (
                EvidenceRef(
                    evidence_id=uuid5(NAMESPACE_URL, f"cpswm:m21:utterance-evidence:{utterance}"),
                    evidence_type="user_query_utterance",
                    source_record_id=source_record_id,
                    locator="compile_argument:utterance",
                ),
            )
        prompt = json.dumps(
            {
                "utterance": utterance,
                "lexicon": [
                    {
                        "canonical_category": item.canonical_category,
                        "aliases": item.aliases,
                        "attributes": item.attributes,
                        "person_entity_ids": [str(value) for value in item.person_entity_ids],
                    }
                    for item in self._lexicon
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        provenance = build_query_compiler_provenance(
            provider="cpswm-local",
            model="deterministic-lexicon-compiler",
            version=self.VERSION,
            temperature=0.0,
            prompt_template_version="deterministic-m21-prompt@1",
            prompt=prompt,
            input_evidence_refs=tuple(item.source_record_id for item in input_evidence_refs),
        )
        normalized = _normalize(utterance)
        matches = tuple(
            entry
            for entry in self._lexicon
            if any(_contains_alias(normalized, alias) for alias in entry.aliases)
        )
        if not normalized or not matches:
            return CompiledSemanticQuery(
                utterance=utterance,
                compiler_model_version=self.VERSION,
                unknown_terms=(utterance.strip() or "<empty>",),
                abstain=True,
                input_evidence_refs=input_evidence_refs,
                invocation_provenance=provenance,
            )

        relations: list[str] = []
        affordances: list[str] = []
        hard_constraints: list[str] = []
        soft_constraints: list[str] = []

        if _has_any(normalized, "where", "where is", "在哪", "哪里", "哪儿"):
            relations.append("located_at")
            hard_constraints.append("answer_current_location")
        if _has_any(normalized, "usually", "normally", "一般", "通常", "习惯"):
            relations.append("habitually_located_at")
            soft_constraints.append("use_habit_distribution")
        if _has_any(normalized, "why", "evidence", "为什么", "证据", "依据"):
            relations.append("supported_by")
            hard_constraints.append("return_evidence_provenance")
        if _has_any(normalized, "history", "before", "曾经", "之前", "历史"):
            relations.append("previously_located_at")
            hard_constraints.append("answer_from_timeline")
        if _has_any(normalized, "next", "will", "接下来", "将会", "预测"):
            relations.append("predicted_location")
            hard_constraints.append("label_as_prediction")
        if _has_any(normalized, "find", "search", "找", "寻找"):
            affordances.append("search")
        if _has_any(normalized, "put", "place", "放", "收纳"):
            affordances.append("place")
        if _has_any(normalized, "ask", "confirm", "问", "确认"):
            affordances.append("ask_user")

        return CompiledSemanticQuery(
            utterance=utterance,
            category_candidates=tuple(dict.fromkeys(entry.canonical_category for entry in matches)),
            attributes=tuple(dict.fromkeys(attr for entry in matches for attr in entry.attributes)),
            relations=tuple(dict.fromkeys(relations)),
            affordances=tuple(dict.fromkeys(affordances)),
            person_entity_ids=tuple(
                dict.fromkeys(
                    person_id for entry in matches for person_id in entry.person_entity_ids
                )
            ),
            time_expression=_time_expression(normalized),
            hard_constraints=tuple(dict.fromkeys(hard_constraints)),
            soft_constraints=tuple(dict.fromkeys(soft_constraints)),
            compiler_model_version=self.VERSION,
            unknown_terms=(),
            abstain=False,
            input_evidence_refs=input_evidence_refs,
            invocation_provenance=provenance,
        )


def _normalize(text: str) -> str:
    return " ".join(text.casefold().strip().split())


def _contains_alias(text: str, alias: str) -> bool:
    normalized_alias = _normalize(alias)
    if not normalized_alias:
        return False
    if re.fullmatch(r"[a-z0-9 _-]+", normalized_alias):
        return re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", text) is not None
    return normalized_alias in text


def _has_any(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def _time_expression(text: str) -> str | None:
    for term in (
        "yesterday",
        "today",
        "tomorrow",
        "morning",
        "afternoon",
        "evening",
        "昨天",
        "今天",
        "明天",
        "早上",
        "上午",
        "下午",
        "晚上",
    ):
        if term in text:
            return term
    return None
