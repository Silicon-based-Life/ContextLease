from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .enums import (
    AllocationStrategy,
    CountMode,
    LifecyclePolicy,
    ProtectionPolicy,
    ReclaimPolicy,
    RenderTarget,
)
from .errors import ConfigurationError
from .models import (
    ArenaDefinition,
    CompressionStepSpec,
    ModelProfile,
    ModuleContribution,
    ModuleDefinition,
    PromptChunk,
)
from .providers import (
    LiteLLMSummaryProvider,
    OpenAICompatibleSummaryProvider,
    SummaryProviderRegistry,
)


_FORBIDDEN_SECRET_KEYS = {"api_key", "authorization", "secret", "token", "password"}
_ROOT_KEYS = {"arena", "model", "providers", "contributions"}
_ARENA_KEYS = {
    "arena_id", "modules", "schema_version", "policy_version",
    "framework_reserve_tokens", "admission_policy", "metadata",
}
_MODULE_KEYS = {
    "module_id", "floor_tokens", "target_tokens", "max_tokens", "order", "weight",
    "lifecycle", "allocation", "protection", "reclaim", "render_target", "can_borrow",
    "can_lend", "reclaim_pipeline", "metadata",
}
_COMPRESSION_STEP_KEYS = {"algorithm_id", "options"}
_MODEL_KEYS = {
    "model_profile_id", "context_limit_tokens", "reserved_output_tokens",
    "tokenizer_id", "tokenizer_version", "count_mode",
}
_CONTRIBUTION_KEYS = {"module_id", "chunks", "observed_demand_tokens", "metadata"}
_CHUNK_KEYS = {
    "chunk_id", "content", "kind", "fixed", "protection", "priority",
    "required_terms", "dependency_group", "metadata",
}
_PROVIDER_COMMON_KEYS = {"type", "model", "api_key_env", "timeout_seconds"}
_PROVIDER_KEYS = {
    "openai-compatible": _PROVIDER_COMMON_KEYS
    | {"base_url", "api_key_header", "api_key_prefix", "extra_headers", "extra_body", "allow_insecure_http"},
    "litellm": _PROVIDER_COMMON_KEYS | {"api_base", "options"},
}


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{path}: expected an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{path}: expected an array")
    return value


def _string(value: Any, path: str, *, non_empty: bool = False) -> str:
    if not isinstance(value, str) or (non_empty and not value):
        qualifier = " a non-empty" if non_empty else ""
        raise ConfigurationError(f"{path}: expected{qualifier} string")
    return value


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{path}: expected an integer")
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{path}: expected a value >= {minimum}")
    return value


def _number(value: Any, path: str, *, exclusive_minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{path}: expected a number")
    result = float(value)
    if exclusive_minimum is not None and result <= exclusive_minimum:
        raise ConfigurationError(f"{path}: expected a value > {exclusive_minimum}")
    return result


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{path}: expected a boolean")
    return value


def _enum(value: Any, enum_type: type, path: str) -> None:
    try:
        enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ConfigurationError(f"{path}: expected one of {allowed}") from exc


def _keys(
    value: Mapping[str, Any],
    *,
    allowed: set[str],
    required: set[str] = frozenset(),
    path: str,
) -> None:
    unknown = sorted(set(map(str, value)) - allowed)
    if unknown:
        raise ConfigurationError(f"{path}: unknown field(s): {', '.join(unknown)}")
    missing = sorted(required - set(value))
    if missing:
        raise ConfigurationError(f"{path}: missing required field(s): {', '.join(missing)}")


def _validate_arena_contract(data: Mapping[str, Any], path: str = "arena") -> None:
    _keys(data, allowed=_ARENA_KEYS, required={"arena_id", "modules"}, path=path)
    _string(data["arena_id"], f"{path}.arena_id", non_empty=True)
    _string(data.get("schema_version", "1.0"), f"{path}.schema_version")
    _string(data.get("policy_version", "1"), f"{path}.policy_version")
    _integer(data.get("framework_reserve_tokens", 0), f"{path}.framework_reserve_tokens", minimum=0)
    _string(data.get("admission_policy", "reject"), f"{path}.admission_policy")
    _object(data.get("metadata", {}), f"{path}.metadata")
    modules = _array(data["modules"], f"{path}.modules")
    if not modules:
        raise ConfigurationError(f"{path}.modules: expected at least one module")
    for index, raw_module in enumerate(modules):
        module_path = f"{path}.modules[{index}]"
        module = _object(raw_module, module_path)
        _keys(
            module,
            allowed=_MODULE_KEYS,
            required={"module_id", "floor_tokens", "target_tokens", "max_tokens"},
            path=module_path,
        )
        _string(module["module_id"], f"{module_path}.module_id", non_empty=True)
        _integer(module["floor_tokens"], f"{module_path}.floor_tokens", minimum=0)
        _integer(module["target_tokens"], f"{module_path}.target_tokens", minimum=0)
        _integer(module["max_tokens"], f"{module_path}.max_tokens", minimum=0)
        _integer(module.get("order", 0), f"{module_path}.order")
        _number(module.get("weight", 1), f"{module_path}.weight", exclusive_minimum=0)
        _enum(module.get("lifecycle", "request"), LifecyclePolicy, f"{module_path}.lifecycle")
        _enum(module.get("allocation", "weighted"), AllocationStrategy, f"{module_path}.allocation")
        _enum(module.get("protection", "mixed"), ProtectionPolicy, f"{module_path}.protection")
        _enum(module.get("reclaim", "builtin_pipeline"), ReclaimPolicy, f"{module_path}.reclaim")
        _enum(module.get("render_target", "text"), RenderTarget, f"{module_path}.render_target")
        _boolean(module.get("can_borrow", True), f"{module_path}.can_borrow")
        _boolean(module.get("can_lend", True), f"{module_path}.can_lend")
        _object(module.get("metadata", {}), f"{module_path}.metadata")
        for step_index, raw_step in enumerate(_array(module.get("reclaim_pipeline", []), f"{module_path}.reclaim_pipeline")):
            step_path = f"{module_path}.reclaim_pipeline[{step_index}]"
            step = _object(raw_step, step_path)
            _keys(step, allowed=_COMPRESSION_STEP_KEYS, required={"algorithm_id"}, path=step_path)
            _string(step["algorithm_id"], f"{step_path}.algorithm_id", non_empty=True)
            _object(step.get("options", {}), f"{step_path}.options")


def _validate_model_contract(data: Mapping[str, Any], path: str = "model") -> None:
    _keys(
        data,
        allowed=_MODEL_KEYS,
        required={"model_profile_id", "context_limit_tokens", "reserved_output_tokens"},
        path=path,
    )
    _string(data["model_profile_id"], f"{path}.model_profile_id", non_empty=True)
    _integer(data["context_limit_tokens"], f"{path}.context_limit_tokens", minimum=1)
    _integer(data["reserved_output_tokens"], f"{path}.reserved_output_tokens", minimum=0)
    _string(data.get("tokenizer_id", "regex-estimator-v1"), f"{path}.tokenizer_id")
    _string(data.get("tokenizer_version", "1"), f"{path}.tokenizer_version")
    _enum(data.get("count_mode", "estimated"), CountMode, f"{path}.count_mode")


def _validate_contributions_contract(values: Any, path: str = "contributions") -> None:
    for index, raw_contribution in enumerate(_array(values, path)):
        contribution_path = f"{path}[{index}]"
        contribution = _object(raw_contribution, contribution_path)
        _keys(
            contribution,
            allowed=_CONTRIBUTION_KEYS,
            required={"module_id", "chunks"},
            path=contribution_path,
        )
        _string(contribution["module_id"], f"{contribution_path}.module_id", non_empty=True)
        if contribution.get("observed_demand_tokens") is not None:
            _integer(
                contribution["observed_demand_tokens"],
                f"{contribution_path}.observed_demand_tokens",
                minimum=0,
            )
        _object(contribution.get("metadata", {}), f"{contribution_path}.metadata")
        for chunk_index, raw_chunk in enumerate(_array(contribution["chunks"], f"{contribution_path}.chunks")):
            chunk_path = f"{contribution_path}.chunks[{chunk_index}]"
            chunk = _object(raw_chunk, chunk_path)
            _keys(chunk, allowed=_CHUNK_KEYS, required={"chunk_id", "content"}, path=chunk_path)
            _string(chunk["chunk_id"], f"{chunk_path}.chunk_id", non_empty=True)
            _string(chunk.get("kind", "text"), f"{chunk_path}.kind")
            _boolean(chunk.get("fixed", False), f"{chunk_path}.fixed")
            _enum(chunk.get("protection", "elastic"), ProtectionPolicy, f"{chunk_path}.protection")
            _number(chunk.get("priority", 1), f"{chunk_path}.priority")
            for term_index, term in enumerate(_array(chunk.get("required_terms", []), f"{chunk_path}.required_terms")):
                _string(term, f"{chunk_path}.required_terms[{term_index}]")
            dependency_group = chunk.get("dependency_group")
            if dependency_group is not None:
                _string(dependency_group, f"{chunk_path}.dependency_group")
            _object(chunk.get("metadata", {}), f"{chunk_path}.metadata")


def _validate_providers_contract(values: Any, path: str = "providers") -> None:
    providers = _object(values, path)
    for provider_id, raw_provider in providers.items():
        provider_path = f"{path}.{provider_id}"
        provider = _object(raw_provider, provider_path)
        provider_type = str(provider.get("type", "openai-compatible"))
        allowed = _PROVIDER_KEYS.get(provider_type)
        if allowed is None:
            raise ConfigurationError(f"unknown summary provider type: {provider_type}")
        required = {"model", "type"}
        if provider_type == "openai-compatible":
            required.add("base_url")
        _keys(provider, allowed=allowed, required=required, path=provider_path)
        _string(provider["type"], f"{provider_path}.type", non_empty=True)
        _string(provider["model"], f"{provider_path}.model", non_empty=True)
        if "api_key_env" in provider:
            _string(provider["api_key_env"], f"{provider_path}.api_key_env", non_empty=True)
        _number(provider.get("timeout_seconds", 30), f"{provider_path}.timeout_seconds", exclusive_minimum=0)
        if provider_type == "openai-compatible":
            _string(provider["base_url"], f"{provider_path}.base_url", non_empty=True)
            _string(provider.get("api_key_header", "Authorization"), f"{provider_path}.api_key_header")
            _string(provider.get("api_key_prefix", "Bearer "), f"{provider_path}.api_key_prefix")
            _object(provider.get("extra_headers", {}), f"{provider_path}.extra_headers")
            _object(provider.get("extra_body", {}), f"{provider_path}.extra_body")
            _boolean(provider.get("allow_insecure_http", False), f"{provider_path}.allow_insecure_http")
        else:
            if "api_base" in provider:
                _string(provider["api_base"], f"{provider_path}.api_base", non_empty=True)
            _object(provider.get("options", {}), f"{provider_path}.options")


def validate_config_contract(data: Mapping[str, Any]) -> None:
    """Validate the strict, versioned JSON configuration shape without third-party dependencies."""
    root = _object(data, "config")
    _keys(root, allowed=_ROOT_KEYS, required={"arena", "model"}, path="config")
    _validate_arena_contract(_object(root["arena"], "config.arena"), "config.arena")
    _validate_model_contract(_object(root["model"], "config.model"), "config.model")
    _validate_providers_contract(root.get("providers", {}), "config.providers")
    _validate_contributions_contract(root.get("contributions", []), "config.contributions")


def _reject_inline_secrets(value: Any, path: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in _FORBIDDEN_SECRET_KEYS:
                raise ConfigurationError(
                    f"{path}.{key}: inline secrets are forbidden; use api_key_env or environment-backed headers"
                )
            _reject_inline_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_inline_secrets(child, f"{path}[{index}]")


def load_json_config(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"failed to load JSON config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("config root must be an object")
    _reject_inline_secrets(data)
    validate_config_contract(data)
    return data


def arena_from_dict(data: Mapping[str, Any]) -> ArenaDefinition:
    data = _object(data, "arena")
    _validate_arena_contract(data)
    modules = []
    for raw in data.get("modules", []):
        pipeline = tuple(
            CompressionStepSpec(str(step["algorithm_id"]), dict(step.get("options", {})))
            for step in raw.get("reclaim_pipeline", [])
        )
        modules.append(
            ModuleDefinition(
                module_id=str(raw["module_id"]),
                floor_tokens=int(raw["floor_tokens"]),
                target_tokens=int(raw["target_tokens"]),
                max_tokens=int(raw["max_tokens"]),
                order=int(raw.get("order", 0)),
                weight=float(raw.get("weight", 1.0)),
                lifecycle=LifecyclePolicy(raw.get("lifecycle", "request")),
                allocation=AllocationStrategy(raw.get("allocation", "weighted")),
                protection=ProtectionPolicy(raw.get("protection", "mixed")),
                reclaim=ReclaimPolicy(raw.get("reclaim", "builtin_pipeline")),
                render_target=RenderTarget(raw.get("render_target", "text")),
                can_borrow=bool(raw.get("can_borrow", True)),
                can_lend=bool(raw.get("can_lend", True)),
                reclaim_pipeline=pipeline,
                metadata=dict(raw.get("metadata", {})),
            )
        )
    return ArenaDefinition(
        arena_id=str(data["arena_id"]),
        modules=tuple(modules),
        schema_version=str(data.get("schema_version", "1.0")),
        policy_version=str(data.get("policy_version", "1")),
        framework_reserve_tokens=int(data.get("framework_reserve_tokens", 0)),
        admission_policy=str(data.get("admission_policy", "reject")),
        metadata=dict(data.get("metadata", {})),
    )


def model_from_dict(data: Mapping[str, Any]) -> ModelProfile:
    data = _object(data, "model")
    _validate_model_contract(data)
    return ModelProfile(
        model_profile_id=str(data["model_profile_id"]),
        context_limit_tokens=int(data["context_limit_tokens"]),
        reserved_output_tokens=int(data["reserved_output_tokens"]),
        tokenizer_id=str(data.get("tokenizer_id", "regex-estimator-v1")),
        tokenizer_version=str(data.get("tokenizer_version", "1")),
        count_mode=CountMode(data.get("count_mode", "estimated")),
    )


def providers_from_dict(data: Mapping[str, Any]) -> SummaryProviderRegistry:
    _reject_inline_secrets(data, "providers")
    _validate_providers_contract(data)
    registry = SummaryProviderRegistry()
    for provider_id, raw in data.items():
        provider_type = str(raw.get("type", "openai-compatible"))
        common = {
            "provider_id": str(provider_id),
            "model": str(raw["model"]),
            "api_key_env": raw.get("api_key_env"),
            "timeout_seconds": float(raw.get("timeout_seconds", 30.0)),
        }
        if provider_type == "openai-compatible":
            provider = OpenAICompatibleSummaryProvider(
                **common,
                base_url=str(raw["base_url"]),
                api_key_header=str(raw.get("api_key_header", "Authorization")),
                api_key_prefix=str(raw.get("api_key_prefix", "Bearer ")),
                extra_headers=dict(raw.get("extra_headers", {})),
                extra_body=dict(raw.get("extra_body", {})),
                allow_insecure_http=bool(raw.get("allow_insecure_http", False)),
            )
        elif provider_type == "litellm":
            provider = LiteLLMSummaryProvider(
                **common,
                api_base=raw.get("api_base"),
                options=dict(raw.get("options", {})),
            )
        else:
            raise ConfigurationError(f"unknown summary provider type: {provider_type}")
        registry.register(provider)
    return registry


def contributions_from_dict(data: Any) -> tuple[ModuleContribution, ...]:
    _validate_contributions_contract(data)
    return tuple(
        ModuleContribution(
            module_id=str(raw["module_id"]),
            chunks=tuple(
                PromptChunk(
                    chunk_id=str(chunk["chunk_id"]),
                    content=chunk["content"],
                    kind=str(chunk.get("kind", "text")),
                    fixed=bool(chunk.get("fixed", False)),
                    protection=ProtectionPolicy(chunk.get("protection", "elastic")),
                    priority=float(chunk.get("priority", 1.0)),
                    required_terms=tuple(map(str, chunk.get("required_terms", []))),
                    dependency_group=chunk.get("dependency_group"),
                    metadata=dict(chunk.get("metadata", {})),
                )
                for chunk in raw["chunks"]
            ),
            observed_demand_tokens=(
                int(raw["observed_demand_tokens"])
                if raw.get("observed_demand_tokens") is not None
                else None
            ),
            metadata=dict(raw.get("metadata", {})),
        )
        for raw in data
    )
