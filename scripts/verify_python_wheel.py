from __future__ import annotations

import argparse
import pathlib
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a ContextLease platform wheel.")
    parser.add_argument("wheel", nargs="?", help="Wheel path; defaults to the only dist/*.whl")
    args = parser.parse_args()
    if args.wheel:
        wheel = pathlib.Path(args.wheel)
    else:
        wheels = list(pathlib.Path("dist").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one wheel under dist, found {len(wheels)}")
        wheel = wheels[0]
    if "-none-any.whl" in wheel.name:
        raise RuntimeError(f"native wheel has a pure-platform tag: {wheel.name}")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    native = [
        name
        for name in names
        if "/contextlease/native/" in f"/{name}"
        and name.endswith((".dll", ".so", ".dylib"))
    ]
    required = "contextlease/schema/contextlease.runtime.schema.json"
    has_runtime_schema = any(name.endswith(required) for name in names)
    if len(native) != 1 or not has_runtime_schema:
        raise RuntimeError(
            f"invalid wheel contents: native={native}, runtime_schema={has_runtime_schema}"
        )
    print(f"ContextLease wheel verified: {wheel.name} ({native[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
