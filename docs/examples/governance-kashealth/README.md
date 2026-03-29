# Governance kashealth.cz -- Reference Implementation

This directory contains a real-world governance document for the
**Medical Platform a Datovy e-shop** project (CZ.01.01.01/01/24_062/0007440, OP TAK).

## What this demonstrates

A complete EDPA deployment for a cross-organizational team comprising
CVUT FBMI and Partner s.r.o., covering:

- **Tooling** -- Microsoft 365 Teams + GitHub (no Jira, no Confluence)
- **Identity** -- kashealth.cz domain with a hybrid member/guest model (5 licensed + guests)
- **EDPA methodology** -- evidence-driven proportional allocation, dual-view (per-person + per-item)
- **SAFe 6 governance** -- Epic Hypothesis Statement, Lean Business Case, WSJF, Kill Criteria, Predictability
- **GitHub Actions** -- 7 automated workflows (WSJF calculator, contributor detection, iteration close, etc.)
- **Implementation plan** -- step-by-step rollout with cost estimates

## Files

| File | Description |
|------|-------------|
| `governance-reseni-v3.md` | Full governance document (v3.0 merged) |

## How to use this example

This governance document can serve as a **template** for:

- EU-funded projects (OP TAK or similar programmes) needing auditable time allocation
- Cross-organizational teams that want GitHub-only governance without Jira/Confluence
- Any project adopting EDPA with SAFe 6 inspired practices

Adapt the identity model, team roster, and cadence configuration to your context.

## Related

- [EDPA methodology documentation](../../docs/)
- [EDPA configuration reference](../../config/)
