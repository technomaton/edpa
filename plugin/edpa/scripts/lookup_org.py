#!/usr/bin/env python3
"""
EDPA Organization Lookup — fetch official company data from public registries.

v1.13 ships with one provider:
  - ARES (CZ) — https://ares.gov.cz public REST API, no auth required.
    Returns: name, legal_name, tax_id (ICO), vat_id (DIC), address, founded
    date, registration status. No phone/email (ARES doesn't carry them).

Future providers (pluggable model — add new function + dispatch in
`lookup_org()`):
  - UK Companies House (CRN lookup, requires API key)
  - EU OpenCorporates (international, freemium API)
  - USA SEC EDGAR (public-company filings only)

Usage:
    # Search by name (returns matches)
    python3 lookup_org.py --search "Medicalc software"

    # Direct lookup by ID
    python3 lookup_org.py --ico 26350513
    python3 lookup_org.py --country CZ --id 26350513

    # Output formats
    python3 lookup_org.py --ico 26350513 --yaml      # YAML org block
    python3 lookup_org.py --ico 26350513 --json      # full machine-readable

    # Apply directly to .edpa/config/edpa.yaml organization slot
    python3 lookup_org.py --ico 26350513 --apply --org-index 1

    # CI / scripted (no interactive prompts)
    python3 lookup_org.py --ico 26350513 --apply --org-index 1 --yes

The standard output dict shape (provider-agnostic):

    {
        "name": str,                # display name
        "legal_name": str,          # full legal name
        "tax_id": str,              # generic — CZ:ICO, USA:EIN, UK:CRN
        "vat_id": str,              # generic — CZ:DIC, EU:VAT-ID, UK:VAT
        "active": bool,             # company status from primary registry
        "founded": str|None,        # YYYY-MM-DD or None
        "address": {
            "street": str, "city": str, "postal_code": str, "country": str
        },
        "contact": {
            "email": "", "phone": "", "website": "",   # always empty here;
                                                       # public registries don't carry these
        },
        "source": str,              # provider identifier ("ARES", "Companies House", ...)
        "source_url": str,          # human-friendly URL to the registry record
        "metadata": dict,           # provider-specific extras (status flags, codes)
    }
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required", file=sys.stderr)
    sys.exit(1)


# ── ARES (CZ) provider ─────────────────────────────────────────────────────


ARES_API_BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"


def _http_get_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"ARES GET {url} failed: {e}", file=sys.stderr)
        return None


def _http_post_json(url: str, body: dict) -> dict | None:
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"ARES POST {url} failed: {e}", file=sys.stderr)
        return None


def _ares_normalize(entity: dict) -> dict:
    """Convert one ARES entity dict to the standard provider-agnostic shape."""
    sidlo = entity.get("sidlo") or {}
    ico = (entity.get("ico") or "").strip()

    # Address — prefer textovaAdresa for the formatted form when available,
    # fallback to manually composing street + city + PSC.
    street = sidlo.get("textovaAdresa", "")
    if not street:
        street_name = sidlo.get("nazevUlice", "")
        cd = sidlo.get("cisloDomovni")
        co = sidlo.get("cisloOrientacni")
        num = ""
        if cd is not None and co is not None:
            num = f"{cd}/{co}"
        elif cd is not None:
            num = str(cd)
        street = f"{street_name} {num}".strip()

    psc = sidlo.get("psc")
    psc_formatted = ""
    if psc is not None:
        s = str(psc)
        # CZ PSČ is 5 digits, conventionally rendered "XXX XX"
        if len(s) == 5:
            psc_formatted = f"{s[:3]} {s[3:]}"
        else:
            psc_formatted = s

    registrations = entity.get("seznamRegistraci") or {}
    primary_active = registrations.get("stavZdrojeRos", "") == "AKTIVNI"

    return {
        "name": entity.get("obchodniJmeno", ""),
        "legal_name": entity.get("obchodniJmeno", ""),
        "tax_id": ico,
        "vat_id": entity.get("dic", ""),
        "active": primary_active,
        "founded": entity.get("datumVzniku"),
        "address": {
            "street": _clean_street_for_address(street, sidlo.get("nazevObce", "")),
            "city": sidlo.get("nazevObce", ""),
            "postal_code": psc_formatted,
            "country": sidlo.get("kodStatu", "CZ"),
        },
        "contact": {
            # ARES does not carry contact details — operator must add manually
            "email": "",
            "phone": "",
            "website": "",
        },
        "source": "ARES",
        "source_url": f"https://ares.gov.cz/ekonomicke-subjekty/?ico={ico}",
        "metadata": {
            "primary_source": entity.get("primarniZdroj", ""),
            "registry_status": registrations.get("stavZdrojeRos", ""),
            "vat_status": registrations.get("stavZdrojeDph", ""),
            "actualized_at": entity.get("datumAktualizace"),
            "legal_form": entity.get("pravniForma", ""),
        },
    }


def _clean_street_for_address(street: str, city: str) -> str:
    """ARES textovaAdresa is `<ulice> <CD/CO>, <obvod>, <PSC obec>`.
    For the structured `address.street` field we want just the street.
    Heuristic: take everything before the first comma."""
    if not street:
        return ""
    return street.split(",")[0].strip()


def lookup_ares(*, ico: str | None = None, name: str | None = None,
                limit: int = 10) -> list[dict]:
    """ARES lookup. Provide ico OR name. Returns list of normalized
    org dicts (single-element when ico is given; up to `limit` matches
    when name is given)."""
    if ico:
        ico = ico.strip()
        if not ico.isdigit() or len(ico) != 8:
            print(f"WARN: ARES expects 8-digit ICO (got {ico!r})", file=sys.stderr)
        url = f"{ARES_API_BASE}/ekonomicke-subjekty/{ico}"
        entity = _http_get_json(url)
        if not entity or "ico" not in entity:
            return []
        return [_ares_normalize(entity)]

    if name:
        url = f"{ARES_API_BASE}/ekonomicke-subjekty/vyhledat"
        result = _http_post_json(url, {"obchodniJmeno": name})
        if not result:
            return []
        entities = result.get("ekonomickeSubjekty", []) or []
        return [_ares_normalize(e) for e in entities[:limit]]

    print("ERROR: lookup_ares requires --ico or --name", file=sys.stderr)
    return []


# ── Provider registry ─────────────────────────────────────────────────────


PROVIDERS: dict[str, Callable] = {
    "CZ": lookup_ares,
}


def lookup_org(*, country: str = "CZ", id_: str | None = None,
               name: str | None = None, limit: int = 10) -> list[dict]:
    """Dispatch to the country-specific provider."""
    provider = PROVIDERS.get(country.upper())
    if not provider:
        print(f"ERROR: no lookup provider for country {country!r}. "
              f"Supported: {sorted(PROVIDERS)}", file=sys.stderr)
        return []
    return provider(ico=id_, name=name, limit=limit)


# ── Output formatters ─────────────────────────────────────────────────────


def format_text(orgs: list[dict]) -> str:
    """Human-readable summary table."""
    if not orgs:
        return "No matches.\n"
    lines = []
    for i, org in enumerate(orgs, 1):
        addr = org["address"]
        lines.append(f"[{i}] {org['name']}")
        lines.append(f"    {org['source']} (status: "
                     f"{'active' if org['active'] else 'inactive'})")
        lines.append(f"    tax_id={org['tax_id']}  vat_id={org['vat_id']}")
        if addr.get("street"):
            full = f"{addr['street']}, {addr.get('postal_code', '')} {addr.get('city', '')}, {addr.get('country', '')}"
            lines.append(f"    {full}")
        if org.get("founded"):
            lines.append(f"    founded: {org['founded']}")
        lines.append(f"    {org['source_url']}")
        lines.append("")
    return "\n".join(lines)


def format_yaml(org: dict, *, role: str = "primary") -> str:
    """Single-org YAML block ready to paste into project.organizations[]."""
    block = {
        "name": org["name"],
        "legal_name": org["legal_name"],
        "role": role,
        "tax_id": org["tax_id"],
        "vat_id": org["vat_id"],
        "address": dict(org["address"]),
        "contact": dict(org["contact"]),
    }
    return yaml.safe_dump([block], default_flow_style=False, allow_unicode=True,
                          sort_keys=False)


def format_json(orgs: list[dict]) -> str:
    return json.dumps(orgs, indent=2, ensure_ascii=False, default=str)


# ── --apply mode ─────────────────────────────────────────────────────────


def apply_to_config(org: dict, config_path: Path, *, org_index: int,
                    role: str = "partner", confirm: bool = True) -> bool:
    """Patch `project.organizations[org_index]` in config_path with org data.

    Preserves contact: fields if the existing entry already has them filled
    (ARES doesn't carry contact info). Returns True when the file was modified.
    """
    if not config_path.is_file():
        print(f"ERROR: config not found at {config_path}", file=sys.stderr)
        return False
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    project = data.setdefault("project", {})
    orgs = project.setdefault("organizations", [])

    # Pad organizations[] if org_index is beyond current length
    while len(orgs) <= org_index:
        orgs.append({})

    existing = orgs[org_index] or {}
    existing_contact = existing.get("contact") or {}

    new_entry = {
        "name": org["name"],
        "legal_name": org["legal_name"],
        "role": existing.get("role") or role,
        "tax_id": org["tax_id"],
        "vat_id": org["vat_id"],
        "address": dict(org["address"]),
        # Preserve any pre-filled contact values (ARES doesn't bring them)
        "contact": {
            "email": existing_contact.get("email", ""),
            "phone": existing_contact.get("phone", ""),
            "website": existing_contact.get("website", ""),
        },
    }

    if confirm:
        print(f"\nWill patch project.organizations[{org_index}] in {config_path}:")
        print(format_yaml(org, role=new_entry["role"]))
        ans = input("Apply? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted.")
            return False

    orgs[org_index] = new_entry
    config_path.write_text(
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True,
                       sort_keys=False),
        encoding="utf-8",
    )
    print(f"✓ Updated {config_path} (organizations[{org_index}])")
    return True


# ── CLI ───────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(
        description="EDPA org lookup — fetch official company data from "
                    "public registries (CZ: ARES; future: UK Companies House, "
                    "EU OpenCorporates).",
    )
    ap.add_argument("--country", default="CZ",
                    help="Country code (ISO 3166-1 alpha-2). Selects provider. "
                         "Default: CZ (ARES). Supported: CZ.")
    ap.add_argument("--ico",
                    help="Direct ICO lookup (CZ shortcut for --id with country=CZ)")
    ap.add_argument("--id", dest="id_",
                    help="Direct ID lookup (uses country-specific provider)")
    ap.add_argument("--search", dest="name",
                    help="Search by company name (returns matches up to --limit)")
    ap.add_argument("--limit", type=int, default=10,
                    help="Max search results (default: 10)")

    # Output formats (mutually exclusive)
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--yaml", action="store_true",
                     help="Output single-org YAML block (works only with --ico/--id "
                          "or first match from --search)")
    fmt.add_argument("--json", action="store_true",
                     help="Output full machine-readable JSON")

    # --apply mode
    ap.add_argument("--apply", action="store_true",
                    help="Patch project.organizations[--org-index] in config "
                         "file with the resolved org data")
    ap.add_argument("--config",
                    default=".edpa/config/edpa.yaml",
                    help="Path to project config (default: .edpa/config/edpa.yaml)")
    ap.add_argument("--org-index", type=int, default=0,
                    help="Index in project.organizations[] to patch (default: 0)")
    ap.add_argument("--role", default="partner",
                    help="role: value when patching (only used if existing entry "
                         "doesn't have one) (default: partner)")
    ap.add_argument("--yes", action="store_true",
                    help="Skip --apply confirmation prompt (CI / scripted)")
    args = ap.parse_args()

    # Normalise --ico into --id with --country=CZ
    id_ = args.id_
    if args.ico:
        id_ = args.ico
        args.country = "CZ"

    if not id_ and not args.name:
        ap.print_help()
        return 1

    orgs = lookup_org(country=args.country, id_=id_, name=args.name,
                      limit=args.limit)
    if not orgs:
        print("No matches.", file=sys.stderr)
        return 1

    if args.apply:
        # Apply requires a single org — use first match (or only result for --ico)
        ok = apply_to_config(orgs[0], Path(args.config),
                             org_index=args.org_index,
                             role=args.role, confirm=not args.yes)
        return 0 if ok else 1

    if args.yaml:
        print(format_yaml(orgs[0], role=args.role))
        return 0
    if args.json:
        print(format_json(orgs))
        return 0

    print(format_text(orgs))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
