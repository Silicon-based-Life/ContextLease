"""Run the ContextLease Debug Web with synthetic, privacy-safe prompt data."""

from __future__ import annotations

import json
import time
from pathlib import Path

from contextlease.cli import contributions_from_config, make_arena
from contextlease.config import model_from_dict
from contextlease.debug import DebugServer


def main() -> None:
    config_path = Path(__file__).with_name("demo.json")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    arena = make_arena(data)
    model = model_from_dict(data["model"])
    contributions = contributions_from_config(data)
    arena.prepare(model, contributions, request_id="demo-initial")

    server = DebugServer(arena.observations, host="127.0.0.1", port=18765).start()
    print(f"ContextLease Debug Web: {server.url}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
