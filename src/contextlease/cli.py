from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from importlib import resources
from pathlib import Path

from .config import arena_from_dict, load_json_config, model_from_dict, providers_from_dict
from .debug import DebugServer
from .enums import ProtectionPolicy
from .layout import compile_layout, validate_model_budget
from .models import ModuleContribution, PromptChunk
from .runtime import ContextLeaseArena


def contributions_from_config(data: dict) -> tuple[ModuleContribution, ...]:
    return tuple(
        ModuleContribution(
            str(raw["module_id"]),
            tuple(
                PromptChunk(
                    chunk_id=str(chunk["chunk_id"]), content=chunk.get("content", ""),
                    kind=str(chunk.get("kind", "text")), fixed=bool(chunk.get("fixed", False)),
                    protection=ProtectionPolicy(chunk.get("protection", "elastic")),
                    priority=float(chunk.get("priority", 1.0)),
                    required_terms=tuple(map(str, chunk.get("required_terms", []))),
                    dependency_group=chunk.get("dependency_group"), metadata=dict(chunk.get("metadata", {})),
                )
                for chunk in raw.get("chunks", [])
            ),
        )
        for raw in data.get("contributions", [])
    )


def command_validate(args: argparse.Namespace) -> int:
    data = load_json_config(args.config)
    arena = arena_from_dict(data["arena"])
    model = model_from_dict(data["model"])
    providers_from_dict(data.get("providers", {}))
    layout = compile_layout(arena)
    validate_model_budget(layout, model.input_budget_tokens)
    print(json.dumps({"status": "valid", "arena_id": arena.arena_id, "layout_hash": layout.layout_hash, "modules": len(arena.modules), "input_budget_tokens": model.input_budget_tokens - arena.framework_reserve_tokens}, ensure_ascii=False, indent=2))
    return 0


def make_arena(data: dict) -> ContextLeaseArena:
    return ContextLeaseArena(arena_from_dict(data["arena"]), summary_providers=providers_from_dict(data.get("providers", {})))


def command_prepare(args: argparse.Namespace) -> int:
    data = load_json_config(args.config)
    result = make_arena(data).prepare(model_from_dict(data["model"]), contributions_from_config(data), request_id=args.request_id)
    print(json.dumps({"status": "completed", "request_id": result.request_id, "prompt_tokens": result.prompt_tokens, "input_budget_tokens": result.input_budget_tokens, "leases": [lease.lease_id for lease in result.leases], "rendered": result.rendered if args.show_content else "<hidden; use --show-content>"}, ensure_ascii=False, indent=2))
    return 0


def command_demo(args: argparse.Namespace) -> int:
    if args.config:
        data = load_json_config(Path(args.config))
    else:
        demo_resource = resources.files("contextlease.examples").joinpath("demo.json")
        try:
            data = json.loads(demo_resource.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"failed to load bundled demo config: {exc}") from exc
    arena = make_arena(data)
    result = arena.prepare(model_from_dict(data["model"]), contributions_from_config(data), request_id="demo-1")
    server = DebugServer(arena.observations, host=args.host, port=args.port).start()
    print(f"ContextLease demo prepared {result.prompt_tokens}/{result.input_budget_tokens} tokens\nDebug Web: {server.url}")
    if args.open:
        webbrowser.open(server.url)
    try:
        print("Press Ctrl+C to stop.")
        while True:
            input()
    except (KeyboardInterrupt, EOFError):
        server.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contextlease", description="Dynamic LLM context budgeting, compression, and observability.")
    parser.add_argument("--version", action="version", version="contextlease 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate a JSON configuration")
    validate.add_argument("config")
    validate.set_defaults(func=command_validate)
    prepare = commands.add_parser("prepare", help="Prepare a prompt from JSON")
    prepare.add_argument("config")
    prepare.add_argument("--request-id")
    prepare.add_argument("--show-content", action="store_true")
    prepare.set_defaults(func=command_prepare)
    demo = commands.add_parser("demo", help="Run the real-time Debug Web demo")
    demo.add_argument("--config")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=8765)
    demo.add_argument("--open", action="store_true")
    demo.set_defaults(func=command_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"contextlease: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
