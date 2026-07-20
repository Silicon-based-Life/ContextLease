# Releasing ContextLease

ContextLease uses one SemVer value across Python, Rust, .NET, native SDK archives,
and `CITATION.cff`.

1. Update `pyproject.toml`, workspace `Cargo.toml`, the managed `.csproj`,
   `CITATION.cff`, `CHANGELOG.md`, and the qualified native library name when required.
2. Run `python scripts/verify_release_versions.py --tag vX.Y.Z`.
3. Run the full CI matrix on a pull request.
4. Create and push the signed or annotated `vX.Y.Z` tag.
5. The Release workflow builds Python packages, the NuGet package, and native SDK
   ZIPs for Windows x86-64, Linux x86-64, and macOS arm64. It then creates a
   GitHub release with SHA-256 checksums.

Registry publication is intentionally separate from GitHub release creation.
Publish PyPI, NuGet, or crates.io packages only from a protected environment with
reviewed tokens and after validating the downloaded release artifacts.
