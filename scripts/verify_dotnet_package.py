from __future__ import annotations

import argparse
import pathlib
import zipfile

from prepare_dotnet_native_assets import ABI, PLATFORMS, VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the ContextLease.Managed NuGet package.")
    parser.add_argument("package", nargs="?", help="Package path; defaults to dist/*.nupkg")
    args = parser.parse_args()
    if args.package:
        package = pathlib.Path(args.package)
    else:
        packages = list(pathlib.Path("dist").glob("ContextLease.Managed.*.nupkg"))
        if len(packages) != 1:
            raise RuntimeError(f"expected one ContextLease.Managed package, found {len(packages)}")
        package = packages[0]
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
    expected = {
        f"runtimes/{rid}/native/{library_name}"
        for rid, library_name in PLATFORMS.values()
    }
    missing = sorted(expected - names)
    if missing:
        raise RuntimeError(f"NuGet package is missing native assets: {missing}")
    if not any(name.endswith("lib/netstandard2.0/ContextLease.Managed.dll") for name in names):
        raise RuntimeError("NuGet package is missing the netstandard2.0 managed assembly")
    print(
        f"ContextLease.Managed {VERSION} verified: ABI {ABI}, "
        f"{len(expected)} RID-native assets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
