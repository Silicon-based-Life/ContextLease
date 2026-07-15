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
