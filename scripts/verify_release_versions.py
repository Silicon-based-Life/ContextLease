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
        "python_module": extract(r'^__version__\s*=\s*"([^"]+)"', ROOT / "src/contextlease/__init__.py"),
        "rust": extract(r'^version\s*=\s*"([^"]+)"', ROOT / "Cargo.toml"),
        "dotnet": extract(r"<Version>([^<]+)</Version>", ROOT / "bindings/dotnet/src/ContextLease.Managed/ContextLease.Managed.csproj"),
        "citation": extract(r"^version:\s*([^\s]+)", ROOT / "CITATION.cff"),
        "native_packager": extract(r'^VERSION\s*=\s*"([^"]+)"', ROOT / "scripts/package_native.py"),
        "dotnet_assets": extract(
            r'^VERSION\s*=\s*"([^"]+)"',
            ROOT / "scripts/prepare_dotnet_native_assets.py",
        ),
    }


def verify_abi() -> None:
    rust = extract(r"^pub const ABI_VERSION:\s*u32\s*=\s*(\d+);", ROOT / "rust/contextlease-ffi/src/lib.rs")
    packager = extract(r'^ABI\s*=\s*"(\d+)"', ROOT / "scripts/package_native.py")
    dotnet_assets = extract(
        r'^ABI\s*=\s*"(\d+)"',
        ROOT / "scripts/prepare_dotnet_native_assets.py",
    )
    dotnet = extract(r"SupportedAbiVersion\s*=\s*(\d+);", ROOT / "bindings/dotnet/src/ContextLease.Managed/ContextLeaseArena.cs")
    go = extract(r"SupportedABIVersion\s+uint32\s*=\s*(\d+)", ROOT / "bindings/go/contextlease.go")
    if len({rust, packager, dotnet_assets, dotnet, go}) != 1:
        raise RuntimeError(
            "ABI mismatch: "
            f"rust={rust}, packager={packager}, dotnet_assets={dotnet_assets}, "
            f"dotnet={dotnet}, go={go}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify ContextLease release version consistency.")
    parser.add_argument("--tag", help="Optional release tag such as v0.3.0")
    args = parser.parse_args(argv)
    try:
        verify_abi()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    versions = collect_versions()
    unique = set(versions.values())
    if len(unique) != 1:
        print("version mismatch: " + ", ".join(f"{key}={value}" for key, value in versions.items()), file=sys.stderr)
        return 1
    version = next(iter(unique))
    abi = extract(
        r"^pub const ABI_VERSION:\s*u32\s*=\s*(\d+);",
        ROOT / "rust/contextlease-ffi/src/lib.rs",
    )
    qualified = extract(
        r'LibraryName\s*=\s*"([^"]+)"',
        ROOT / "bindings/dotnet/src/ContextLease.Managed/NativeMethods.cs",
    )
    expected_qualified = f"contextlease_native_abi{abi}_v{version.replace('.', '_')}"
    if qualified != expected_qualified:
        print(
            f"qualified native name mismatch: expected {expected_qualified}, found {qualified}",
            file=sys.stderr,
        )
        return 1
    if args.tag and args.tag.removeprefix("v") != version:
        print(f"tag {args.tag} does not match version {version}", file=sys.stderr)
        return 1
    print(f"ContextLease release metadata is consistent: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
