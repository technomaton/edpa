# Security Policy

EDPA is a Claude Code plugin that installs git hooks (`commit-msg`,
`pre-commit`, `post-commit`) into your project and installs Python
dependencies when a session starts. Anything that lets those surfaces do
more than they document — arbitrary code execution beyond the documented
hooks, path traversal out of the project root, or exfiltration of
repository contents by the engine scripts, MCP server, or CI workflows —
is in scope for a security report.

## Supported versions

Only the latest release is supported. Security fixes ship as a new
release on `main`; older releases do not receive backports. Please
update to the latest release and reproduce there before reporting.

## Reporting a vulnerability

Please do **not** report security vulnerabilities through public GitHub
issues, discussions, or pull requests.

1. **Preferred:** use GitHub private vulnerability reporting — the
   [Report a vulnerability](https://github.com/technomaton/edpa/security/advisories/new)
   button under the repository's **Security** tab.
2. **Fallback:** email the maintainer at
   [urbanek.jaroslav@gmail.com](mailto:urbanek.jaroslav@gmail.com) with
   `[EDPA security]` in the subject line.

A useful report includes:

- the affected component (plugin scripts, vendored `.edpa/engine/`
  scripts, git hooks, MCP server, CI workflows, website),
- reproduction steps or a proof of concept,
- the impact you believe it has.

## What to expect

- Acknowledgement within 7 days.
- For confirmed issues, a fix or mitigation plan within 90 days,
  shipped as a new release.
- Coordinated disclosure: please give the maintainer a chance to
  release a fix before publishing details. You will be credited in the
  release notes unless you prefer otherwise.

## Out of scope

- Vulnerabilities in your own project's code that EDPA merely versions
  or reports on.
- Issues that require an attacker who can already write to your
  repository or execute code on your machine.
- Vulnerabilities only present in unsupported (non-latest) releases.
