from .builtin import FunctionAlgorithm, builtin_algorithms, truncate_text_to_tokens
from .contracts import CompressionAlgorithm, CompressionRequest, CompressionResult
from .pipeline import CompressionPipeline
from .registry import CompressionRegistry


def create_builtin_registry() -> CompressionRegistry:
    return CompressionRegistry(builtin_algorithms())


__all__ = [
    "CompressionAlgorithm", "CompressionPipeline", "CompressionRegistry", "CompressionRequest",
    "CompressionResult", "FunctionAlgorithm", "builtin_algorithms", "create_builtin_registry",
    "truncate_text_to_tokens",
]
