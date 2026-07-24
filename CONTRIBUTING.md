# Contributing

Thanks for helping improve ContextLease.

By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md). Support and security reports follow the
routes in [SUPPORT.md](SUPPORT.md) and [SECURITY.md](SECURITY.md).

## Development setup

```bash
git clone https://github.com/Silicon-based-Life/ContextLease.git
cd contextlease
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

On macOS/Linux, activate with `source .venv/bin/activate`.

Rust 1.75 or newer is required for source and editable installs because the
Python package builds the native kernel. Install Node.js, Go, and .NET only when
changing their corresponding surfaces.

## Validation

Run the checks for every surface affected by the change:

```bash
ruff check src tests scripts
python -m compileall -q src
python -m unittest discover -s tests -v
python scripts/verify_release_versions.py

cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

node --check src/contextlease/debug/static/app.js
node --check docs/site.js

cd bindings/go
gofmt -l .
go vet ./...
go test ./...

dotnet build bindings/dotnet/src/ContextLease.Managed/ContextLease.Managed.csproj \
  -c Release -warnaserror
```

The C and C++ smoke programs are built in CI with warnings treated as errors.
Release changes must also build the wheel, execute
`scripts/verify_installed_wheel.py`, and validate every packaged consumer.

## Dependency updates and Rust MSRV

ContextLease supports Rust 1.75 as its minimum supported Rust version (MSRV).
Cargo dependency updates must pass both forms of the `rust-msrv` CI check:

- the committed `Cargo.lock`, using `cargo check --workspace --all-targets --locked`;
- a fresh dependency resolution after removing `Cargo.lock`.

Dependabot groups Cargo patch releases only. Minor and major releases remain
isolated for review because a `0.x` minor release can contain breaking API or
MSRV changes. The `sha2` dependency intentionally stays on the compatible
`0.10.x` line. Moving it to `0.11` or later requires one focused pull request
that updates the API usage, the declared MSRV, CI, and compatibility notes
together; remove the matching Dependabot ignore rule only as part of that
migration.

## Pull requests

1. Keep the core dependency-free unless there is a documented architectural reason.
2. Add tests for allocator, reclaim, provider, schema, or telemetry behavior changes.
3. Never add provider keys or real prompt data to fixtures.
4. Preserve stable algorithm IDs and public event fields, or document a versioned migration.
5. Run the unit suite, Python compile check, and JavaScript syntax checks before submitting.
6. Update shared fixtures when behavior must match across languages.
7. Describe Schema, Rust behavior, ABI, binding, and packaging impact explicitly.
8. Update `CHANGELOG.md` for user-visible changes.

Bug reports should include a minimal arena/model definition, demands, expected allocation, and observed allocation. Replace prompt content with synthetic text.

## Compatibility changes

Read [docs/stability.md](docs/stability.md) before changing a public DTO, enum,
algorithm identifier, native function, ownership rule, or artifact name.
Compatibility changes require:

- an updated schema and DTO parity test;
- Rust and Python/native conformance evidence;
- affected binding and consumer tests;
- version and migration notes where required.

Do not silently repurpose a reserved field or algorithm identifier.

## Commit and review scope

Keep pull requests focused. Formatting-only or dependency-only changes should
not be mixed with behavior changes. A maintainer may ask to split a change when
it obscures compatibility or review risk.

The project does not currently require a CLA or DCO sign-off. Contributions are
accepted under the repository's Apache-2.0 terms.
