from __future__ import annotations

import argparse
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = "0.3.0"
ABI = "2"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a ContextLease native SDK archive.")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--library", required=True, type=pathlib.Path)
    parser.add_argument("--output", default="dist", type=pathlib.Path)
    args = parser.parse_args()

    library = (ROOT / args.library).resolve() if not args.library.is_absolute() else args.library
    if not library.is_file():
        raise FileNotFoundError(library)
    output = (ROOT / args.output).resolve() if not args.output.is_absolute() else args.output
    output.mkdir(parents=True, exist_ok=True)
    package_name = f"contextlease-native-{args.platform}-v{VERSION}"
    stage = output / package_name
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "include").mkdir(parents=True)
    (stage / "lib").mkdir(parents=True)
    shutil.copy2(ROOT / "bindings/c/include/contextlease.h", stage / "include/contextlease.h")
    shutil.copy2(ROOT / "bindings/cpp/include/contextlease.hpp", stage / "include/contextlease.hpp")
    qualified = library.name.replace("contextlease_native", f"contextlease_native_abi{ABI}_v{VERSION.replace('.', '_')}")
    shutil.copy2(library, stage / "lib" / qualified)
    for candidate in library.parent.glob("*contextlease_native*"):
        if candidate == library or not candidate.is_file():
            continue
        if candidate.suffix.lower() in {".a", ".lib"} or candidate.name.endswith(".dll.lib"):
            shutil.copy2(candidate, stage / "lib" / candidate.name)
    for name in ("LICENSE", "NOTICE", "README.md"):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copy2(ROOT / "docs/native-bindings.md", stage / "NATIVE_BINDINGS.md")
    archive = shutil.make_archive(str(output / package_name), "zip", output, package_name)
    shutil.rmtree(stage)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
