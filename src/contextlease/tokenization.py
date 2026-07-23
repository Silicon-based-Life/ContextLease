from __future__ import annotations

import json
import re
from typing import Any, Protocol


class TokenCounter(Protocol):
    counter_id: str

    def count_text(self, text: str) -> int: ...

    def count_content(self, content: Any) -> int: ...


class RegexTokenCounter:
    """Deterministic dependency-free estimator for tests and local planning.

    Production hosts should inject the tokenizer used by their target model.
    """

    counter_id = "regex-estimator-v1"
    _pattern = re.compile(r"[\w]+|[^\w\s]", re.UNICODE)

    def count_text(self, text: str) -> int:
        return len(self._pattern.findall(text or ""))

    def count_content(self, content: Any) -> int:
        if isinstance(content, str):
            return self.count_text(content)
        if content is None:
            return 0
        serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return self.count_text(serialized)


class CharacterTokenCounter:
    """Predictable counter useful for golden tests and embedded hosts."""

    counter_id = "character-v1"

    def count_text(self, text: str) -> int:
        return len(text or "")

    def count_content(self, content: Any) -> int:
        if isinstance(content, str):
            return self.count_text(content)
        return self.count_text(json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


class TiktokenTokenCounter:
    """Exact OpenAI-family tokenizer adapter for the native host callback.

    Install with ``pip install 'contextlease[tokenizers]'``. Prefer an explicit
    encoding name for long-lived production profiles; model mappings can evolve.
    """

    def __init__(self, *, encoding_name: str | None = None, model: str | None = None) -> None:
        if bool(encoding_name) == bool(model):
            raise ValueError("provide exactly one of encoding_name or model")
        try:
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "tiktoken is not installed; install contextlease[tokenizers]"
            ) from exc
        self._encoding = (
            tiktoken.get_encoding(encoding_name)
            if encoding_name
            else tiktoken.encoding_for_model(model)
        )
        self.counter_id = f"tiktoken:{self._encoding.name}"

    def count_text(self, text: str) -> int:
        return len(self._encoding.encode(text or "", disallowed_special=()))

    def count_content(self, content: Any) -> int:
        if isinstance(content, str):
            return self.count_text(content)
        serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return self.count_text(serialized)
