# Changelog

All notable changes are documented here. The project follows Semantic Versioning.

## [Unreleased]

### Added

- Public contribution, conduct, support, maintainer, ownership, and stability policies.
- GitHub issue forms, pull-request template, dependency updates, secret scanning,
  dependency audits, and Python CodeQL workflow.
- Installed-wheel execution smoke and stronger lint/build gates.

### Changed

- GitHub Actions dependencies are pinned to immutable commits.
- GitHub Pages waits for public repository visibility and can enable Pages on deployment.
- Removed stale internal framework-review artifacts from the published documentation tree.

## [0.3.0] - 2026-07-22

### Added

- Established the Rust kernel as the canonical allocator, reclaim engine, and telemetry owner.
- Added versioned `ContextPlan` / `PreparedContextPlan` structured runtime contracts.
- Added ABI v2 host tokenizer callbacks and actual-usage EWMA calibration.
- Added native snapshot/event pull APIs across C, C++, Go, Python, and .NET.
- Changed Python builds to platform wheels that bundle the native kernel.
- Added a cross-language contract fixture covering previously drifting fields and
  canonical layout-hash parity.
- Added richer native prepared-context allocation, lease, model, tokenizer, and
  module-usage telemetry.

### Fixed

- Used isolated PEP 517 builds in CI so Python 3.12-3.14 and wheel jobs do not
  depend on runner-preinstalled `setuptools`.
- Aligned public Python enum values with the bundled JSON Schema while retaining
  source-compatible alpha aliases.
- Preserved lifecycle, allocation, reclaim, render-target, model-counting,
  metadata, and chunk-kind fields in the Rust core.
- Rejected unknown configuration fields in both Python and Rust.
- Derived the CLI version from package metadata rather than a stale literal.

## [0.2.0] - 2026-07-20

### Added

- Canonical Rust allocation, lease, reclaim, and rendering core with stable C ABI v1.
- C, C++, Go, Python, .NET, and Unity native bindings with shared conformance fixtures.
- Two-phase host-provider semantic compression with required-term and hard-budget validation.
- Cross-platform CI, native SDK archives, NuGet packaging, release metadata checks, and
  GitHub Release automation.

## [0.1.0] - 2026-07-15

### Added

- Floor/target/max token budgets with weighted allocation.
- Donor-attributed, revocable token leases and demand-driven reclaim.
- Twelve deterministic and two semantic compression algorithms.
- OpenAI-compatible, optional LiteLLM, and callable summary providers.
- Required-term, monotonicity, and target-size validation.
- Content-free snapshots, bounded event traces, REST, SSE, and Debug Web.
- JSON configuration, packaged schema, CLI validation, preparation, and demo commands.
