---
description: Export billable hours to CSV for payroll / invoicing (Xero, QuickBooks)
allowed-tools: Read, Bash
model: sonnet
---

# EDPA Export

Export billable hours from an engine run to a CSV file suitable for payroll
or invoicing systems (Xero, QuickBooks, grant reporting).

`$ARGUMENTS` is `csv <iteration-id> [options]`.

Output columns: `iteration, person, name, role, team, hours, rate, currency, cost, code`

Examples:
- `csv PI-2026-1.1` — export iteration PI-2026-1.1 to `.edpa/reports/iteration-PI-2026-1.1/payroll-PI-2026-1.1.csv`
- `csv PI-2026-1.1 --currency CZK` — override currency for all rows
- `csv PI-2026-1.1 --output /tmp/invoice.csv` — custom output path

**Options:**
- `--currency CODE` — currency code override for rows where `currency` is not set in `people.yaml` (e.g. `CZK`, `EUR`, `USD`)
- `--output PATH` — output file path (default: `.edpa/reports/iteration-<id>/payroll-<id>.csv`)

## Prerequisites

`/edpa:engine` must have been run for the target iteration — the export reads
`.edpa/reports/iteration-<id>/edpa_results.json`.

For costs to appear in the `cost` column, add `hourly_rate` to each person
in `.edpa/config/people.yaml`:
```yaml
- id: urbanek
  name: J. Urbanek
  role: Arch
  hourly_rate: 1500
  currency: CZK
```

## Steps

1. Parse `$ARGUMENTS`. Confirm action is `csv`. Extract iteration ID (required — ask if missing).

2. Run the export script:
   ```bash
   python3 .edpa/engine/scripts/payroll_export.py \
     --iteration <ITERATION-ID> \
     [--currency <CODE>] \
     [--output <PATH>] \
     --edpa-root .edpa
   ```

3. Report the output path, row count, and total hours. If `rate` is missing for some
   people, note which ones and remind the user to add `hourly_rate` to `people.yaml`.

4. Offer to open the CSV in the shell:
   ```bash
   open <path>   # macOS
   # or: xdg-open <path>  # Linux
   ```

## Notes

- The `code` column is populated from `project.funding.registration` in `.edpa/config/edpa.yaml`
  (or `project.registration` for legacy configs). This is the grant/contract code used in
  external billing systems.
- Missing `hourly_rate` → `rate` and `cost` columns are empty for that person. The CSV
  is still valid; the rate can be filled in post-export.
- Rows are sorted by team, then person ID.
- The export is read-only and idempotent — re-running overwrites the previous CSV.
