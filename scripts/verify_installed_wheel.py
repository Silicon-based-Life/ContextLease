from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import tempfile
import venv

SMOKE = r"""
import json
from contextlease import NativeArena

definition = {
    "arena_id": "installed-wheel",
    "modules": [
        {
            "module_id": "memory",
            "floor_tokens": 0,
            "target_tokens": 8,
            "max_tokens": 8,
        }
    ],
}
request = {
    "request_id": "wheel-smoke",
    "model": {
        "model_profile_id": "estimated",
        "context_limit_tokens": 8,
        "reserved_output_tokens": 0,
    },
    "contributions": [
        {
            "module_id": "memory",
            "chunks": [{"chunk_id": "fact", "content": "alpha beta"}],
        }
    ],
}
with NativeArena(definition) as arena:
    prepared = arena.prepare(request)
    abi = arena.abi_version
assert prepared["request_id"] == "wheel-smoke"
assert prepared["prompt_tokens"] <= prepared["input_budget_tokens"]
assert prepared["module_plans"][0]["module_id"] == "memory"
print(json.dumps({"abi": abi, "request_id": prepared["request_id"]}))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and execute a built ContextLease wheel.")
    parser.add_argument("wheel", nargs="?", help="Wheel path; defaults to the only dist/*.whl")
    args = parser.parse_args()
    if args.wheel:
        wheel = pathlib.Path(args.wheel).resolve()
    else:
        wheels = list(pathlib.Path("dist").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one wheel under dist, found {len(wheels)}")
        wheel = wheels[0].resolve()

    with tempfile.TemporaryDirectory(prefix="contextlease-wheel-") as temp:
        root = pathlib.Path(temp)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        if (environment / "Scripts" / "python.exe").is_file():
            python = environment / "Scripts" / "python.exe"
        else:
            python = environment / "bin" / "python"
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
            check=True,
        )
        completed = subprocess.run(
            [str(python), "-c", SMOKE],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout.strip())
        if result["abi"] != 2:
            raise RuntimeError(f"unexpected installed native ABI: {result}")
    print(f"Installed wheel smoke passed: {wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
