"""In-process binding for the Rust ContextLease core.

The high-level Python implementation remains available while the Rust migration
is staged.  This module is the stable bridge used by cross-language conformance
tests and by applications that opt into the native core.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
from pathlib import Path
from typing import Any, Mapping


class NativeContextLeaseError(RuntimeError):
    pass


def _library_name() -> str:
    system = platform.system()
    if system == "Windows":
        return "contextlease_native.dll"
    if system == "Darwin":
        return "libcontextlease_native.dylib"
    return "libcontextlease_native.so"


def _candidate_paths() -> list[Path]:
    override = os.environ.get("CONTEXTLEASE_NATIVE_LIBRARY")
    candidates = [Path(override)] if override else []
    package_dir = Path(__file__).resolve().parent
    candidates.extend((package_dir / _library_name(), package_dir / "native" / _library_name()))
    return candidates


def _load_library(path: str | os.PathLike[str] | None = None) -> ctypes.CDLL:
    candidates = [Path(path)] if path else _candidate_paths()
    for candidate in candidates:
        if candidate.is_file():
            return ctypes.CDLL(str(candidate))
    raise NativeContextLeaseError(
        "ContextLease native library was not found; set CONTEXTLEASE_NATIVE_LIBRARY"
    )


class NativeArena:
    """Owns one opaque Rust arena handle and prepares JSON-compatible requests."""

    def __init__(self, definition: Mapping[str, Any], *, library_path: str | None = None) -> None:
        self._lib = _load_library(library_path)
        self._configure_abi()
        self._handle = ctypes.c_void_p()
        payload = json.dumps(definition, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        code = self._lib.cl_arena_create(payload, ctypes.byref(self._handle))
        self._check(code)

    @property
    def abi_version(self) -> int:
        return int(self._lib.cl_abi_version())

    def prepare(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self._handle:
            raise NativeContextLeaseError("native arena is closed")
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result_ptr = ctypes.c_void_p()
        code = self._lib.cl_arena_prepare(self._handle, payload, ctypes.byref(result_ptr))
        self._check(code)
        try:
            text = ctypes.string_at(result_ptr).decode("utf-8")
            return json.loads(text)
        finally:
            self._lib.cl_string_free(result_ptr)

    def prepare_begin(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Begin a two-phase prepare and return ready output or semantic requests."""
        if not self._handle:
            raise NativeContextLeaseError("native arena is closed")
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result_ptr = ctypes.c_void_p()
        code = self._lib.cl_arena_prepare_begin(self._handle, payload, ctypes.byref(result_ptr))
        self._check(code)
        try:
            return json.loads(ctypes.string_at(result_ptr).decode("utf-8"))
        finally:
            self._lib.cl_string_free(result_ptr)

    def prepare_commit(
        self,
        request: Mapping[str, Any],
        semantic_results: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Commit validated host provider results and render the prepared context."""
        if not self._handle:
            raise NativeContextLeaseError("native arena is closed")
        request_payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        results_payload = json.dumps(semantic_results, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result_ptr = ctypes.c_void_p()
        code = self._lib.cl_arena_prepare_commit(
            self._handle,
            request_payload,
            results_payload,
            ctypes.byref(result_ptr),
        )
        self._check(code)
        try:
            return json.loads(ctypes.string_at(result_ptr).decode("utf-8"))
        finally:
            self._lib.cl_string_free(result_ptr)

    def close(self) -> None:
        if self._handle:
            self._lib.cl_arena_free(self._handle)
            self._handle = ctypes.c_void_p()

    def __enter__(self) -> "NativeArena":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _configure_abi(self) -> None:
        self._lib.cl_abi_version.restype = ctypes.c_uint32
        self._lib.cl_arena_create.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self._lib.cl_arena_create.restype = ctypes.c_int32
        self._lib.cl_arena_prepare.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self._lib.cl_arena_prepare.restype = ctypes.c_int32
        self._lib.cl_arena_prepare_begin.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self._lib.cl_arena_prepare_begin.restype = ctypes.c_int32
        self._lib.cl_arena_prepare_commit.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._lib.cl_arena_prepare_commit.restype = ctypes.c_int32
        self._lib.cl_arena_free.argtypes = [ctypes.c_void_p]
        self._lib.cl_string_free.argtypes = [ctypes.c_void_p]
        self._lib.cl_last_error.restype = ctypes.c_char_p

    def _check(self, code: int) -> None:
        if code == 0:
            return
        raw = self._lib.cl_last_error()
        detail = raw.decode("utf-8", errors="replace") if raw else f"native error {code}"
        raise NativeContextLeaseError(detail)
