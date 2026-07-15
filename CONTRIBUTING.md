# Contributing

Thanks for helping improve ContextLease.

## Development setup

```bash
git clone https://github.com/yuexiong/contextlease.git
cd contextlease
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## Pull requests

1. Keep the core dependency-free unless there is a documented architectural reason.
2. Add tests for allocator, reclaim, provider, schema, or telemetry behavior changes.
3. Never add provider keys or real prompt data to fixtures.
4. Preserve stable algorithm IDs and public event fields, or document a versioned migration.
5. Run the unit suite, Python compile check, and JavaScript syntax checks before submitting.

Bug reports should include a minimal arena/model definition, demands, expected allocation, and observed allocation. Replace prompt content with synthetic text.
