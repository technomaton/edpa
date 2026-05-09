# Organization Lookup (v1.13+)

`plugin/edpa/scripts/lookup_org.py` fetches official company data from
public business registries to fill the `project.organizations[]` block
in `.edpa/config/edpa.yaml` without manual re-keying.

## Providers (current)

| Country | Provider | API | Auth | Fields returned |
|---------|----------|-----|------|-----------------|
| **CZ** | ARES | https://ares.gov.cz public REST | none | name, legal_name, tax_id (ICO), vat_id (DIC), legal seat address, founded date, registry status |

**Future providers** (pluggable model — add a function to `PROVIDERS`
dict in lookup_org.py):
- **UK**: Companies House — CRN lookup, requires API key
- **EU**: OpenCorporates — international, freemium API
- **USA**: SEC EDGAR — public-company filings only

## Usage

### Look up by ID (direct)

```bash
# CZ shorthand: --ico maps to --country=CZ --id=<ICO>
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513

# Generic form (works for future non-CZ providers)
python3 .claude/edpa/scripts/lookup_org.py --country CZ --id 26350513
```

Output (default text format):
```
[1] Medicalc software s.r.o.
    ARES (status: active)
    tax_id=26350513  vat_id=CZ26350513
    Pod Švabinami 434/13, 312 00 Plzeň, CZ
    founded: 2002-11-07
    https://ares.gov.cz/ekonomicke-subjekty/?ico=26350513
```

### Search by name

```bash
python3 .claude/edpa/scripts/lookup_org.py --search "Medicalc software"
python3 .claude/edpa/scripts/lookup_org.py --search "ČVUT" --limit 5
```

### Output formats

```bash
# YAML block ready to paste into project.organizations[]
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513 --yaml --role partner

# Full JSON (all metadata, machine-readable)
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513 --json
```

`--yaml` example output:
```yaml
- name: Medicalc software s.r.o.
  legal_name: Medicalc software s.r.o.
  role: partner
  tax_id: '26350513'
  vat_id: CZ26350513
  address:
    street: Pod Švabinami 434/13
    city: Plzeň
    postal_code: 312 00
    country: CZ
  contact:
    email: ''
    phone: ''
    website: ''
```

### --apply (patch config directly)

```bash
# Interactive (default config path .edpa/config/edpa.yaml, org-index 0)
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513 --apply

# Specify which org slot to patch
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513 --apply --org-index 1 --role partner

# CI / scripted (skip confirmation)
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513 --apply --org-index 1 --yes

# Custom config path
python3 .claude/edpa/scripts/lookup_org.py --ico 26350513 --apply --config /path/to/edpa.yaml
```

`--apply` semantics:
- Pads `project.organizations[]` with empty entries if `--org-index` is
  beyond current length.
- **Preserves existing contact info** (email/phone/website) — ARES
  doesn't carry contact details, so any operator-set values must
  survive the patch.
- **Preserves existing role** if the slot already has one set;
  otherwise uses `--role` (default `partner`).
- Replaces identity fields (name, legal_name, tax_id, vat_id, address)
  with registry data.
- Prints diff + asks for confirmation unless `--yes` is set.

## ARES-specific notes

### What ARES carries

- ICO (8-digit company ID)
- DIC (CZ + 8-digit VAT ID — only when company is VAT-registered)
- Official name (`obchodniJmeno`)
- Legal seat (sídlo) — full structured address
- Date of incorporation
- Legal form code
- Status flags per registry (ROS, VR, RES, RZP, DPH, NRPZS, RPSH, ...)
- CZ-NACE codes (industry classification)
- Last update timestamp

### What ARES does NOT carry

- Email, phone, website — operator must add manually
- Director / statutory body composition — separate API endpoint
- Bank accounts — not public

### Sídlo vs operating offices

ARES `sidlo` is the **legal seat** — used for invoicing, grant
reporting, court jurisdiction. Some companies operate from a
different physical office.

For ČVUT (Czech Technical University) the ARES sídlo is the rectorate
in Praha. Faculties (FBMI in Kladno, FEL in Praha 6, etc.) don't have
separate ICOs — they operate under the university's legal entity. For
audit reference use ČVUT Praha (legal); for operational comms use the
faculty's own address.

### VAT status (DPH)

`vat_id` is populated by ARES only when company has active VAT
registration (`stavZdrojeDph: AKTIVNI`). Inactive or non-registered
companies have empty `vat_id`.

## Adding a new provider

To support a new country (e.g., UK):

1. Add a function `lookup_uk_companies_house(ico=None, name=None,
   limit=10) -> list[dict]` in `lookup_org.py` that calls the UK API.
2. Make it return the standard provider-agnostic dict shape (same as
   `_ares_normalize` output).
3. Register it: `PROVIDERS["GB"] = lookup_uk_companies_house`.
4. Add tests to `tests/test_lookup_org.py` mocking the UK API
   responses.

The CLI dispatches automatically on `--country`. No CLI changes
needed.

## Tests

```bash
python3 -m pytest tests/test_lookup_org.py -v
```

30 tests cover ARES response normalization, output formatters
(text/yaml/json), `--apply` mode (padding, contact preservation, role
preservation, missing config), and provider registry contract. HTTP
calls are mocked so tests don't hit live ARES.
