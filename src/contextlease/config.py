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
    ModuleDefinition,
)
from .providers import (
    LiteLLMSummaryProvider,
    OpenAICompatibleSummaryProvider,
    SummaryProviderRegistry,
)


_FORBIDDEN_SECRET_KEYS = {"api_key", "authorization", "secret", "token", "password"}


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
    return data


def arena_from_dict(data: Mapping[str, Any]) -> ArenaDefinition:
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
