# Security policy

## Supported versions

Security fixes are applied to the latest released minor version.

## Reporting a vulnerability

Please use GitHub's private
[Report a vulnerability](https://github.com/Silicon-based-Life/ContextLease/security/advisories/new)
flow instead of opening a public issue. Include the affected version,
reproduction, impact, and any proposed mitigation. Do not include live
credentials or private prompt content.

The project aims to acknowledge a report within three business days and provide
an initial triage within seven business days. Resolution and disclosure timing
depend on severity, release impact, and coordination with the reporter. These
targets are best-effort rather than a contractual SLA.

## Security posture

- Configuration rejects common inline secret fields; use environment-variable names.
- Public observation DTOs do not contain prompt bodies.
- Debug Web is loopback-only by default and requires a bearer token for non-loopback binds.
- Provider responses are validated as compression candidates, not trusted as authoritative state.
- ContextLease performs no telemetry export and has no required runtime dependency.

The Debug Web is a development observability surface, not an internet-facing administration console.

## Disclosure

Please allow maintainers a reasonable opportunity to validate and release a fix
before public disclosure. Credit is provided when requested and safe to do so.
