from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib import error, parse, request

from ..errors import ConfigurationError, ProviderError
from .base import SummaryRequest, SummaryResponse


@dataclass(slots=True)
class OpenAICompatibleSummaryProvider:
    provider_id: str
    model: str
    base_url: str
    api_key_env: str | None = None
    timeout_seconds: float = 30.0
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    extra_body: Mapping[str, Any] = field(default_factory=dict)
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        parsed = parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ConfigurationError("summary provider base_url must use http or https")
        is_local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (self.allow_insecure_http or is_local):
            raise ConfigurationError("non-local summary provider URLs must use https")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("timeout_seconds must be positive")

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def summarize(self, summary_request: SummaryRequest) -> SummaryResponse:
        headers = {"Content-Type": "application/json", **dict(self.extra_headers)}
        if self.api_key_env:
            api_key = os.getenv(self.api_key_env)
            if not api_key:
                raise ProviderError(f"environment variable {self.api_key_env!r} is not set")
            headers[self.api_key_header] = f"{self.api_key_prefix}{api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You compress LLM context. Preserve required terms and factual qualifiers. "
                        "Return only the compressed text; do not add commentary."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Target tokens: {summary_request.target_tokens}\n"
                        f"Required terms: {', '.join(summary_request.required_terms) or '(none)'}\n"
                        f"Instructions: {summary_request.instructions}\n\n"
                        f"CONTENT\n{summary_request.content}"
                    ),
                },
            ],
            "temperature": summary_request.temperature,
            "max_tokens": summary_request.target_tokens,
            **dict(self.extra_body),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise ProviderError(f"provider returned HTTP {exc.code}: {detail}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"provider request failed: {exc}") from exc

        try:
            text = decoded["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("provider response did not contain choices[0].message.content") from exc
        usage = decoded.get("usage") or {}
        return SummaryResponse(
            text=str(text).strip(),
            provider_id=self.provider_id,
            model=self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            metadata={"endpoint": self.endpoint},
        )
