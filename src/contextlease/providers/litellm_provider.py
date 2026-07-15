from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import ProviderError
from .base import SummaryRequest, SummaryResponse


@dataclass(slots=True)
class LiteLLMSummaryProvider:
    """Bring-your-own LiteLLM adapter; LiteLLM is never a Core dependency."""

    provider_id: str
    model: str
    api_key_env: str | None = None
    api_base: str | None = None
    timeout_seconds: float = 30.0
    options: Mapping[str, Any] = field(default_factory=dict)

    def summarize(self, request: SummaryRequest) -> SummaryResponse:
        try:
            from litellm import completion  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderError(
                "LiteLLM is not installed. Install and audit it separately before using this adapter."
            ) from exc
        api_key = os.getenv(self.api_key_env) if self.api_key_env else None
        if self.api_key_env and not api_key:
            raise ProviderError(f"environment variable {self.api_key_env!r} is not set")
        try:
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Compress context and return only the summary."},
                    {
                        "role": "user",
                        "content": (
                            f"Target tokens: {request.target_tokens}\n"
                            f"Required terms: {', '.join(request.required_terms) or '(none)'}\n"
                            f"Instructions: {request.instructions}\n\n{request.content}"
                        ),
                    },
                ],
                max_tokens=request.target_tokens,
                temperature=request.temperature,
                timeout=self.timeout_seconds,
                api_key=api_key,
                api_base=self.api_base,
                **dict(self.options),
            )
            text = response.choices[0].message.content
            usage = getattr(response, "usage", None)
        except Exception as exc:  # LiteLLM maps provider errors into its own hierarchy.
            raise ProviderError(f"LiteLLM provider request failed: {exc}") from exc
        return SummaryResponse(
            text=str(text).strip(),
            provider_id=self.provider_id,
            model=self.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )
