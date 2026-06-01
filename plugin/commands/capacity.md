---
description: View or set per-iteration per-person capacity overrides (PTO, overtime, ramp)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Capacity Override

A person's baseline capacity per iteration comes from `.edpa/config/people.yaml`
(`capacity_per_iteration`, fallback `capacity`). This command adjusts it for **one
iteration** — PTO, sick leave, overtime, onboarding ramp — without touching the
baseline. Overrides live in the iteration YAML `people:` block and are applied by
the engine, surfacing in `edpa_results.json` as `capacity`, `capacity_baseline`,
and `capacity_override`.

The first argument is the iteration id (e.g. `PI-2026-1.4`), then an action.

## Steps

1. **List** current overrides:
```bash
python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --list
```

2. **Set / change** an override — absolute hours, or a `+N` / `-N` delta from baseline:
```bash
# absolute (2.5 days PTO → 20h):
python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --add --person <id> --hours 20  --note "PTO 2.5 days"
# delta down (sick):
python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --add --person <id> --hours -12 --note "sick"
# delta up (overtime):
python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --add --person <id> --hours +8  --note "release push"
```

3. **Remove** an override (revert to baseline):
```bash
python3 .edpa/engine/scripts/capacity_override.py <iteration-id> --remove --person <id>
```

## Notes

- `--person` must be an `id` from `people.yaml`. `--note` is the audit reason (empty string = explicit waiver).
- Each change is validated and auto-committed (`<iter>: capacity override <person> -> <hours>h (<note>)`); pass `--no-commit` to only touch the file.
- **Closed iterations reject overrides** (audit trail) — set them BEFORE closing. The same prep is Stage 1 of `/edpa:close-iteration` (`<iter> --prep-only`).
- For a permanent capacity change across all iterations, edit `capacity_per_iteration` in `people.yaml` instead.
- After changing capacity, re-run `/edpa:engine <iteration-id>` so reports reflect the new allocation.
