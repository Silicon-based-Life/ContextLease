# Releasing ContextLease

ContextLease uses one SemVer value across Python, Rust, .NET, native SDK archives,
and `CITATION.cff`.

1. Update `pyproject.toml`, workspace `Cargo.toml`, the managed `.csproj`,
   `CITATION.cff`, `CHANGELOG.md`, and the qualified native library name when required.
2. Run `python scripts/verify_release_versions.py --tag vX.Y.Z`.
3. Run the full CI matrix on a pull request.
4. Create and push the signed or annotated `vX.Y.Z` tag.
5. The Release workflow builds the Python sdist plus Rust-bundled platform wheels,
   the NuGet package with RID-native assets, and native SDK ZIPs for Windows
   x86-64, Linux x86-64, and macOS arm64. It validates each artifact in an
   isolated consumer, attests the public tagged build, and creates a GitHub
   release with SHA-256 checksums.

Registry publication is intentionally separate from GitHub release creation.
Configure PyPI Trusted Publishing through GitHub OIDC and a protected deployment
environment; do not add a long-lived PyPI token when OIDC is available. NuGet or
crates.io publication must likewise run from a protected, reviewed environment
after validating the downloaded GitHub release artifacts. Registry setup and the
first publication are explicit maintainer/admin actions.

The Go binding is a nested module at `bindings/go`. If it is published through the
repository, use a matching subdirectory tag such as `bindings/go/v0.3.0`, only
after its conformance job has passed. A root `v0.3.0` tag alone does not version
the nested Go module for consumers.
