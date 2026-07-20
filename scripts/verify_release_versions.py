from __future__ import annotations

import argparse
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def extract(pattern: str, path: pathlib.Path) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError(f"version not found in {path.relative_to(ROOT)}")
    return match.group(1)


def collect_versions() -> dict[str, str]:
    return {
        "python": extract(r'^version\s*=\s*"([^"]+)"', ROOT / "pyproject.toml"),
        "rust": extract(r'^version\s*=\s*"([^"]+)"', ROOT / "Cargo.toml"),
        "dotnet": extract(r"<Version>([^<]+)</Version>", ROOT / "bindings/dotnet/src/ContextLease.Managed/ContextLease.Managed.csproj"),
        "citation": extract(r"^version:\s*([^\s]+)", ROOT / "CITATION.cff"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify ContextLease release version consistency.")
    parser.add_argument("--tag", help="Optional release tag such as v0.2.0")
    args = parser.parse_args(argv)
    versions = collect_versions()
    unique = set(versions.values())
    if len(unique) != 1:
        print("version mismatch: " + ", ".join(f"{key}={value}" for key, value in versions.items()), file=sys.stderr)
        return 1
    version = next(iter(unique))
    if args.tag and args.tag.removeprefix("v") != version:
        print(f"tag {args.tag} does not match version {version}", file=sys.stderr)
        return 1
    print(f"ContextLease release metadata is consistent: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
