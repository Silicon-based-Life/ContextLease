# Stability and compatibility

ContextLease is currently an alpha-stage `0.x` project. It is suitable for
evaluation and controlled integrations, but public APIs may still change
between minor releases.

## Compatibility surfaces

ContextLease treats the following as versioned public contracts:

- JSON configuration and runtime schemas;
- Rust public types and behavior;
- native C ABI functions, ownership rules, and error codes;
- Python, C++, Go, and .NET binding APIs;
- compression algorithm identifiers;
- event and snapshot DTOs;
- release artifact names and platform layout.

## Version policy

- One release version is shared across Python, Rust, .NET, native SDK archives,
  and `CITATION.cff`.
- The native ABI has an independent integer version. A binding rejects an
  unsupported ABI before creating an arena.
- Additive schema fields may appear in a minor release only when old readers
  can safely ignore them. Strict input schemas otherwise require an explicit
  migration.
- Breaking behavior, removed fields, ownership changes, or renamed algorithm
  identifiers require a documented migration and a release-version change.
- Security fixes may require a compatibility exception; the release notes must
  state it explicitly.

## Deprecation

Before `1.0`, the project aims to announce avoidable breaking changes in
`CHANGELOG.md` for at least one minor release. After `1.0`, public API removals
should remain deprecated for at least one minor release unless a security issue
requires faster removal.

## What is not stable

Debug Web presentation details, internal trace wording, benchmark numbers, and
undocumented implementation types are not compatibility contracts.

Consumers should pin an exact version and keep local conformance fixtures for
their prompt layouts and model/tokenizer combinations.
