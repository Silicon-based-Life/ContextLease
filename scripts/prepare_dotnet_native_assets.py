from __future__ import annotations

import argparse
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = "0.3.0"
ABI = "2"
PROJECT = ROOT / "bindings" / "dotnet" / "src" / "ContextLease.Managed"
PLATFORMS = {
    "linux-x86_64": (
        "linux-x64",
        f"libcontextlease_native_abi{ABI}_v{VERSION.replace('.', '_')}.so",
    ),
    "windows-x86_64": (
        "win-x64",
        f"contextlease_native_abi{ABI}_v{VERSION.replace('.', '_')}.dll",
    ),
    "macos-arm64": (
        "osx-arm64",
        f"libcontextlease_native_abi{ABI}_v{VERSION.replace('.', '_')}.dylib",
    ),
}


def prepare_assets(artifacts: pathlib.Path, project: pathlib.Path = PROJECT) -> list[pathlib.Path]:
    runtimes = project / "runtimes"
    if runtimes.exists():
        shutil.rmtree(runtimes)
    written: list[pathlib.Path] = []
    for platform_name, (rid, library_name) in PLATFORMS.items():
        archive_name = f"contextlease-native-{platform_name}-v{VERSION}.zip"
        matches = list(artifacts.rglob(archive_name))
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one {archive_name} under {artifacts}, found {len(matches)}"
            )
        with zipfile.ZipFile(matches[0]) as archive:
            members = [name for name in archive.namelist() if name.endswith(f"/lib/{library_name}")]
            if len(members) != 1:
                raise RuntimeError(
                    f"expected one {library_name} in {matches[0]}, found {members}"
                )
            target = runtimes / rid / "native" / library_name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(members[0]) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare RID-native assets for ContextLease.Managed."
    )
    parser.add_argument("--artifacts", required=True, type=pathlib.Path)
    parser.add_argument("--project", type=pathlib.Path, default=PROJECT)
    args = parser.parse_args()
    written = prepare_assets(args.artifacts.resolve(), args.project.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
