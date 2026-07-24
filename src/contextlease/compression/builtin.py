from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..errors import CompressionError
from ..providers import SummaryProviderRegistry, SummaryRequest
from .contracts import CompressionRequest, CompressionResult

AlgorithmFunction = Callable[[CompressionRequest], tuple[Any, Sequence[Any], Mapping[str, Any]]]


def _contains_required(content: Any, required_terms: Iterable[str]) -> bool:
    haystack = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    folded = haystack.casefold()
    return all(term.casefold() in folded for term in required_terms)


def _result(
    algorithm_id: str,
    request: CompressionRequest,
    content: Any,
    removed: Sequence[Any] = (),
    trace: Mapping[str, Any] | None = None,
    *,
    lossy: bool,
) -> CompressionResult:
    before = request.counter.count_content(request.content)
    after = request.counter.count_content(content)
    if not _contains_required(content, request.required_terms):
        return CompressionResult(
            algorithm_id, request.content, before, before, "required_terms_blocked", lossy, trace=trace or {}
        )
    if after > before:
        return CompressionResult(
            algorithm_id, request.content, before, before, "non_monotonic_rejected", lossy, trace=trace or {}
        )
    return CompressionResult(
        algorithm_id,
        content,
        before,
        after,
        "target_met" if after <= request.target_tokens else "compressed",
        lossy,
        tuple(removed),
        trace or {},
    )


@dataclass(frozen=True, slots=True)
class FunctionAlgorithm:
    algorithm_id: str
    lossy: bool
    function: AlgorithmFunction

    def compress(self, request: CompressionRequest) -> CompressionResult:
        content, removed, trace = self.function(request)
        return _result(
            self.algorithm_id, request, content, removed, trace, lossy=self.lossy
        )


def _normalize_whitespace(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, str):
        return request.content, (), {"status": "unsupported_type"}
    preserve_fences = bool(request.options.get("preserve_fenced_blocks", True))
    segments = re.split(r"(```.*?```)", request.content, flags=re.DOTALL) if preserve_fences else [request.content]
    normalized = []
    for segment in segments:
        if preserve_fences and segment.startswith("```"):
            normalized.append(segment.strip())
        else:
            lines = [re.sub(r"[ \t]+", " ", line).strip() for line in segment.splitlines()]
            normalized.append(re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip())
    return "\n".join(part for part in normalized if part), (), {}


def _deduplicate_blocks(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, str):
        return request.content, (), {"status": "unsupported_type"}
    blocks = [block.strip() for block in re.split(r"\n\s*\n", request.content) if block.strip()]
    seen: set[str] = set()
    kept: list[str] = []
    removed: list[str] = []
    for block in blocks:
        key = re.sub(r"\s+", " ", block).casefold()
        (removed if key in seen else kept).append(block)
        seen.add(key)
    return "\n\n".join(kept), removed, {"removed_blocks": len(removed)}


def _structured_minify(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if isinstance(request.content, str):
        try:
            value = json.loads(request.content)
        except json.JSONDecodeError:
            return request.content, (), {"status": "invalid_json"}
    elif isinstance(request.content, (dict, list)):
        value = request.content
    else:
        return request.content, (), {"status": "unsupported_type"}
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True), (), {}


def _exact_deduplicate(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, list):
        return request.content, (), {"status": "unsupported_type"}
    seen: set[str] = set()
    kept, removed = [], []
    for item in request.content:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        (removed if key in seen else kept).append(item)
        seen.add(key)
    return kept, removed, {"removed_items": len(removed)}


def _similarity_deduplicate(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    threshold = float(request.options.get("threshold", 0.88))
    if isinstance(request.content, str):
        items: list[Any] = [part.strip() for part in re.split(r"\n\s*\n", request.content) if part.strip()]
        join_text = True
    elif isinstance(request.content, list):
        items = request.content
        join_text = False
    else:
        return request.content, (), {"status": "unsupported_type"}
    kept, removed = [], []
    fingerprints: list[str] = []
    for item in items:
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
        fingerprint = re.sub(r"\s+", " ", text).casefold()
        if any(SequenceMatcher(None, fingerprint, prior).ratio() >= threshold for prior in fingerprints):
            removed.append(item)
        else:
            kept.append(item)
            fingerprints.append(fingerprint)
    return ("\n\n".join(kept) if join_text else kept), removed, {"threshold": threshold}


def _item_content(item: Any) -> Any:
    if isinstance(item, dict) and "content" in item:
        return item["content"]
    return item


def _priority_select(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, list):
        return request.content, (), {"status": "unsupported_type"}
    indexed = list(enumerate(request.content))
    ranked = sorted(
        indexed,
        key=lambda pair: (
            -float(pair[1].get("priority", 0.0)) if isinstance(pair[1], dict) else 0.0,
            pair[0],
        ),
    )
    selected: list[tuple[int, Any]] = []
    for pair in ranked:
        candidate = [item for _, item in sorted(selected + [pair])]
        if request.counter.count_content(candidate) <= request.target_tokens or not selected:
            selected.append(pair)
    selected_ids = {index for index, _ in selected}
    kept = [item for index, item in indexed if index in selected_ids]
    removed = [item for index, item in indexed if index not in selected_ids]
    return kept, removed, {"selection": "priority"}


def _recency_select(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, list):
        return request.content, (), {"status": "unsupported_type"}
    kept_reversed: list[Any] = []
    for item in reversed(request.content):
        candidate = list(reversed(kept_reversed + [item]))
        if request.counter.count_content(candidate) <= request.target_tokens or not kept_reversed:
            kept_reversed.append(item)
    kept = list(reversed(kept_reversed))
    kept_ids = {id(item) for item in kept}
    removed = [item for item in request.content if id(item) not in kept_ids]
    return kept, removed, {"selection": "recency"}


def _extractive_sentence_rank(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, str):
        return request.content, (), {"status": "unsupported_type"}
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|\n+", request.content) if part.strip()]
    words = re.findall(r"[\w]+", request.content.casefold())
    frequencies = Counter(word for word in words if len(word) > 2)
    ranked = []
    for index, sentence in enumerate(sentences):
        score = sum(frequencies[word] for word in re.findall(r"[\w]+", sentence.casefold()))
        score += 1000 * sum(term.casefold() in sentence.casefold() for term in request.required_terms)
        ranked.append((score / max(1, math.sqrt(len(sentence))), index, sentence))
    selected: list[tuple[int, str]] = []
    for _, index, sentence in sorted(ranked, reverse=True):
        candidate = " ".join(text for _, text in sorted(selected + [(index, sentence)]))
        if request.counter.count_text(candidate) <= request.target_tokens or not selected:
            selected.append((index, sentence))
    result = " ".join(text for _, text in sorted(selected))
    selected_indices = {index for index, _ in selected}
    removed = [sentence for index, sentence in enumerate(sentences) if index not in selected_indices]
    return result, removed, {"sentences": len(sentences), "selected": len(selected)}


def truncate_text_to_tokens(text: str, target: int, counter: Any, keep: str = "head") -> str:
    if target <= 0:
        return ""
    if counter.count_text(text) <= target:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = text[-mid:] if keep == "tail" else text[:mid]
        if counter.count_text(candidate) <= target:
            low = mid
        else:
            high = mid - 1
    candidate = text[-low:] if keep == "tail" else text[:low]
    if keep == "tail":
        boundary = re.search(r"\s", candidate)
        return candidate[boundary.end():] if boundary else candidate
    boundary = max(candidate.rfind(" "), candidate.rfind("\n"))
    return candidate[:boundary] if boundary > len(candidate) // 2 else candidate


def _boundary_truncate(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, str):
        return request.content, (), {"status": "unsupported_type"}
    keep = str(request.options.get("keep", "head"))
    truncated = truncate_text_to_tokens(request.content, request.target_tokens, request.counter, keep)
    removed = request.content[len(truncated):] if keep == "head" else request.content[:-len(truncated)]
    return truncated, (removed,) if removed else (), {"keep": keep}


def _field_prune(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, dict):
        return request.content, (), {"status": "unsupported_type"}
    protected = set(request.options.get("protected_fields", ()))
    priorities = dict(request.options.get("field_priorities", {}))
    result = dict(request.content)
    removed = []
    candidates = sorted(
        (key for key in result if key not in protected),
        key=lambda key: (float(priorities.get(key, 0.0)), key),
    )
    while request.counter.count_content(result) > request.target_tokens and candidates:
        key = candidates.pop(0)
        removed.append((key, result.pop(key)))
    return result, removed, {"protected_fields": sorted(protected)}


def _message_group_select(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    if not isinstance(request.content, list) or not all(isinstance(item, dict) for item in request.content):
        return request.content, (), {"status": "unsupported_type"}
    groups: list[list[dict]] = []
    group_index: dict[str, int] = {}
    for index, message in enumerate(request.content):
        key = str(
            message.get("dependency_group")
            or message.get("tool_call_id")
            or message.get("id")
            or f"message:{index}"
        )
        if key not in group_index:
            group_index[key] = len(groups)
            groups.append([])
        groups[group_index[key]].append(message)
    pinned = [group for group in groups if any(item.get("role") == "system" for item in group)]
    selected = list(pinned)
    for group in reversed(groups):
        if group in selected:
            continue
        candidate = [item for candidate_group in selected + [group] for item in candidate_group]
        if request.counter.count_content(candidate) <= request.target_tokens or not selected:
            selected.append(group)
    selected_ids = {id(group) for group in selected}
    kept_groups = [group for group in groups if id(group) in selected_ids]
    removed_groups = [group for group in groups if id(group) not in selected_ids]
    return [item for group in kept_groups for item in group], removed_groups, {"atomic_groups": len(groups)}


def _reference_externalize(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    reference_id = str(request.options.get("reference_id") or request.metadata.get("content_hash") or "external")
    placeholder = str(request.options.get("template", "[Context reference: {reference_id}]")).format(
        reference_id=reference_id
    )
    return placeholder, (request.content,), {"reference_id": reference_id}


def _semantic_summary(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    registry = request.services.get("summary_providers")
    if not isinstance(registry, SummaryProviderRegistry):
        raise CompressionError("semantic summary requires a SummaryProviderRegistry service")
    provider_id = str(request.options.get("provider"))
    if not provider_id or provider_id == "None":
        raise CompressionError("semantic summary step requires options.provider")
    provider = registry.get(provider_id)
    content = request.content if isinstance(request.content, str) else json.dumps(request.content, ensure_ascii=False)
    response = provider.summarize(
        SummaryRequest(
            content=content,
            target_tokens=request.target_tokens,
            instructions=str(request.options.get("instructions", "Preserve facts, qualifiers, and unresolved items.")),
            required_terms=request.required_terms,
            temperature=float(request.options.get("temperature", 0.0)),
            metadata=request.metadata,
        )
    )
    result = response.text.strip()
    if request.counter.count_text(result) > request.target_tokens:
        result = truncate_text_to_tokens(result, request.target_tokens, request.counter)
    return result, (request.content,), {
        "provider_id": response.provider_id,
        "model": response.model,
        "provider_input_tokens": response.input_tokens,
        "provider_output_tokens": response.output_tokens,
    }


def _semantic_portfolio(request: CompressionRequest) -> tuple[Any, Sequence[Any], Mapping[str, Any]]:
    provider_ids = tuple(request.options.get("providers", ()))
    if not provider_ids:
        raise CompressionError("semantic portfolio requires options.providers")
    candidates = []
    for provider_id in provider_ids:
        candidate_request = CompressionRequest(
            content=request.content,
            target_tokens=request.target_tokens,
            counter=request.counter,
            required_terms=request.required_terms,
            options={**request.options, "provider": provider_id},
            services=request.services,
            metadata=request.metadata,
        )
        candidate, _, trace = _semantic_summary(candidate_request)
        if _contains_required(candidate, request.required_terms):
            candidates.append((request.counter.count_content(candidate), str(provider_id), candidate, trace))
    if not candidates:
        raise CompressionError("no semantic portfolio candidate passed required-term validation")
    _, provider_id, content, trace = min(candidates, key=lambda item: (item[0], item[1]))
    return content, (request.content,), {**trace, "selected_provider": provider_id, "candidate_count": len(candidates)}


def builtin_algorithms() -> tuple[FunctionAlgorithm, ...]:
    return (
        FunctionAlgorithm("builtin.text.normalize_whitespace.v1", False, _normalize_whitespace),
        FunctionAlgorithm("builtin.text.deduplicate_blocks.v1", False, _deduplicate_blocks),
        FunctionAlgorithm("builtin.structured.minify.v1", False, _structured_minify),
        FunctionAlgorithm("builtin.collection.exact_deduplicate.v1", False, _exact_deduplicate),
        FunctionAlgorithm("builtin.collection.similarity_deduplicate.v1", True, _similarity_deduplicate),
        FunctionAlgorithm("builtin.collection.priority_select.v1", True, _priority_select),
        FunctionAlgorithm("builtin.collection.recency_select.v1", True, _recency_select),
        FunctionAlgorithm("builtin.text.extractive_sentence_rank.v1", True, _extractive_sentence_rank),
        FunctionAlgorithm("builtin.text.boundary_truncate.v1", True, _boundary_truncate),
        FunctionAlgorithm("builtin.structured.field_prune.v1", True, _field_prune),
        FunctionAlgorithm("builtin.message.group_select.v1", True, _message_group_select),
        FunctionAlgorithm("builtin.reference.externalize.v1", True, _reference_externalize),
        FunctionAlgorithm("builtin.semantic.summary.v1", True, _semantic_summary),
        FunctionAlgorithm("builtin.semantic.portfolio.v1", True, _semantic_portfolio),
    )
