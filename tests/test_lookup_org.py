"""Unit tests for lookup_org.py — ARES response parsing, output formatters,
and --apply mode patching. HTTP calls are mocked so tests don't hit the live
ARES API."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent /
                      "plugin" / "edpa" / "scripts"))

import lookup_org as lo  # noqa: E402


# ── Sample ARES responses (real shape, from production) ───────────────────


MEDICALC_ARES_RESPONSE = {
    "ico": "26350513",
    "obchodniJmeno": "Medicalc software s.r.o.",
    "sidlo": {
        "kodStatu": "CZ",
        "nazevStatu": "Česká republika",
        "kodKraje": 43,
        "nazevKraje": "Plzeňský kraj",
        "kodObce": 554791,
        "nazevObce": "Plzeň",
        "kodMestskeCastiObvodu": 546208,
        "nazevMestskeCastiObvodu": "Plzeň 4",
        "nazevUlice": "Pod Švabinami",
        "cisloDomovni": 434,
        "cisloOrientacni": 13,
        "kodCastiObce": 490300,
        "nazevCastiObce": "Lobzy",
        "psc": 31200,
        "textovaAdresa": "Pod Švabinami 434/13, Lobzy, 31200 Plzeň",
    },
    "pravniForma": "112",
    "datumVzniku": "2002-11-07",
    "datumAktualizace": "2025-05-11",
    "dic": "CZ26350513",
    "primarniZdroj": "ros",
    "seznamRegistraci": {
        "stavZdrojeRos": "AKTIVNI",
        "stavZdrojeDph": "AKTIVNI",
    },
}


SEARCH_RESULT = {
    "pocetCelkem": 1,
    "ekonomickeSubjekty": [MEDICALC_ARES_RESPONSE],
}


# ── _ares_normalize ───────────────────────────────────────────────────────


def test_normalize_extracts_basic_fields():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    assert org["name"] == "Medicalc software s.r.o."
    assert org["legal_name"] == "Medicalc software s.r.o."
    assert org["tax_id"] == "26350513"
    assert org["vat_id"] == "CZ26350513"
    assert org["active"] is True
    assert org["founded"] == "2002-11-07"
    assert org["source"] == "ARES"


def test_normalize_address_split():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    addr = org["address"]
    # textovaAdresa has full string; we split off just the street part
    assert addr["street"] == "Pod Švabinami 434/13"
    assert addr["city"] == "Plzeň"
    assert addr["country"] == "CZ"


def test_normalize_postal_code_formatted():
    """CZ PSČ stored as int 31200; rendered as 'XXX XX'."""
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    assert org["address"]["postal_code"] == "312 00"


def test_normalize_contact_always_empty():
    """ARES doesn't carry contact details — stays empty for operator to fill."""
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    assert org["contact"]["email"] == ""
    assert org["contact"]["phone"] == ""
    assert org["contact"]["website"] == ""


def test_normalize_metadata():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    md = org["metadata"]
    assert md["primary_source"] == "ros"
    assert md["registry_status"] == "AKTIVNI"
    assert md["vat_status"] == "AKTIVNI"
    assert md["actualized_at"] == "2025-05-11"


def test_normalize_source_url():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    assert org["source_url"] == "https://ares.gov.cz/ekonomicke-subjekty/?ico=26350513"


def test_normalize_handles_missing_address():
    minimal = {"ico": "12345678", "obchodniJmeno": "Empty s.r.o.", "sidlo": {}}
    org = lo._ares_normalize(minimal)
    assert org["address"]["street"] == ""
    assert org["address"]["city"] == ""
    assert org["address"]["country"] == "CZ"  # default


def test_normalize_inactive_status():
    inactive = dict(MEDICALC_ARES_RESPONSE)
    inactive["seznamRegistraci"] = {"stavZdrojeRos": "ZRUSENY"}
    org = lo._ares_normalize(inactive)
    assert org["active"] is False


# ── lookup_ares (HTTP mocked) ──────────────────────────────────────────────


def test_lookup_ares_by_ico_success():
    with patch.object(lo, "_http_get_json", return_value=MEDICALC_ARES_RESPONSE):
        results = lo.lookup_ares(ico="26350513")
    assert len(results) == 1
    assert results[0]["tax_id"] == "26350513"


def test_lookup_ares_by_ico_not_found():
    with patch.object(lo, "_http_get_json", return_value=None):
        results = lo.lookup_ares(ico="99999999")
    assert results == []


def test_lookup_ares_by_ico_returns_empty_on_missing_ico_field():
    """ARES sometimes returns 200 with a body that doesn't have an `ico` field
    (e.g., for invalid IDs). Treat as no-match."""
    with patch.object(lo, "_http_get_json", return_value={"error": "not found"}):
        results = lo.lookup_ares(ico="00000000")
    assert results == []


def test_lookup_ares_by_name_returns_matches():
    with patch.object(lo, "_http_post_json", return_value=SEARCH_RESULT):
        results = lo.lookup_ares(name="Medicalc software")
    assert len(results) == 1
    assert results[0]["name"] == "Medicalc software s.r.o."


def test_lookup_ares_by_name_respects_limit():
    multi = {"ekonomickeSubjekty": [MEDICALC_ARES_RESPONSE] * 5}
    with patch.object(lo, "_http_post_json", return_value=multi):
        results = lo.lookup_ares(name="Medicalc", limit=3)
    assert len(results) == 3


def test_lookup_ares_requires_ico_or_name(capsys):
    results = lo.lookup_ares()
    assert results == []
    err = capsys.readouterr().err
    assert "requires --ico or --name" in err


def test_lookup_ares_warns_on_invalid_ico_format(capsys):
    with patch.object(lo, "_http_get_json", return_value=MEDICALC_ARES_RESPONSE):
        lo.lookup_ares(ico="abc123")
    err = capsys.readouterr().err
    assert "8-digit ICO" in err


# ── lookup_org dispatch ────────────────────────────────────────────────────


def test_lookup_org_dispatches_cz_to_ares():
    with patch.object(lo, "_http_get_json", return_value=MEDICALC_ARES_RESPONSE):
        results = lo.lookup_org(country="CZ", id_="26350513")
    assert len(results) == 1
    assert results[0]["source"] == "ARES"


def test_lookup_org_unknown_country(capsys):
    results = lo.lookup_org(country="ZZ", id_="123")
    assert results == []
    err = capsys.readouterr().err
    assert "no lookup provider" in err
    assert "ZZ" in err


def test_lookup_org_country_case_insensitive():
    """`--country cz` works the same as `--country CZ`."""
    with patch.object(lo, "_http_get_json", return_value=MEDICALC_ARES_RESPONSE):
        results = lo.lookup_org(country="cz", id_="26350513")
    assert len(results) == 1


# ── Output formatters ──────────────────────────────────────────────────────


def test_format_text_includes_key_fields():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    text = lo.format_text([org])
    assert "Medicalc software s.r.o." in text
    assert "26350513" in text
    assert "CZ26350513" in text
    assert "Plzeň" in text
    assert "active" in text


def test_format_text_empty_list():
    assert lo.format_text([]) == "No matches.\n"


def test_format_yaml_produces_valid_yaml():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    text = lo.format_yaml(org, role="primary")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "Medicalc software s.r.o."
    assert parsed[0]["role"] == "primary"
    assert parsed[0]["tax_id"] == "26350513"


def test_format_yaml_role_override():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    text = lo.format_yaml(org, role="subcontractor")
    assert "role: subcontractor" in text


def test_format_json_produces_valid_json():
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    text = lo.format_json([org])
    parsed = json.loads(text)
    assert isinstance(parsed, list)
    assert parsed[0]["tax_id"] == "26350513"


# ── apply_to_config ───────────────────────────────────────────────────────


def test_apply_creates_org_at_index(tmp_path):
    cfg = tmp_path / "edpa.yaml"
    cfg.write_text(yaml.safe_dump({
        "project": {"name": "Test", "organizations": []},
    }))
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    ok = lo.apply_to_config(org, cfg, org_index=0, role="partner", confirm=False)
    assert ok
    data = yaml.safe_load(cfg.read_text())
    assert data["project"]["organizations"][0]["tax_id"] == "26350513"
    assert data["project"]["organizations"][0]["role"] == "partner"


def test_apply_pads_organizations_list(tmp_path):
    cfg = tmp_path / "edpa.yaml"
    cfg.write_text(yaml.safe_dump({
        "project": {"name": "Test", "organizations": [{"name": "Existing"}]},
    }))
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    lo.apply_to_config(org, cfg, org_index=2, role="partner", confirm=False)
    data = yaml.safe_load(cfg.read_text())
    # Index 0 preserved, index 1 padded with {}, index 2 = our org
    assert len(data["project"]["organizations"]) == 3
    assert data["project"]["organizations"][0]["name"] == "Existing"
    assert data["project"]["organizations"][2]["tax_id"] == "26350513"


def test_apply_preserves_existing_contact(tmp_path):
    """ARES doesn't bring contact info — operator-set values must survive
    --apply patches."""
    cfg = tmp_path / "edpa.yaml"
    cfg.write_text(yaml.safe_dump({
        "project": {"name": "Test", "organizations": [{
            "name": "Old Name",
            "contact": {"email": "ops@old.cz", "phone": "+420 111 222 333",
                        "website": "https://old.cz"},
        }]},
    }))
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    lo.apply_to_config(org, cfg, org_index=0, role="partner", confirm=False)
    data = yaml.safe_load(cfg.read_text())
    contact = data["project"]["organizations"][0]["contact"]
    assert contact["email"] == "ops@old.cz"  # preserved
    assert contact["phone"] == "+420 111 222 333"
    assert contact["website"] == "https://old.cz"
    # But identity was replaced
    assert data["project"]["organizations"][0]["name"] == "Medicalc software s.r.o."


def test_apply_preserves_existing_role(tmp_path):
    """If existing entry already has a role: value, --apply respects it
    over the --role default."""
    cfg = tmp_path / "edpa.yaml"
    cfg.write_text(yaml.safe_dump({
        "project": {"organizations": [{"role": "consortium-lead"}]},
    }))
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    lo.apply_to_config(org, cfg, org_index=0, role="partner", confirm=False)
    data = yaml.safe_load(cfg.read_text())
    assert data["project"]["organizations"][0]["role"] == "consortium-lead"


def test_apply_returns_false_when_config_missing(tmp_path, capsys):
    cfg = tmp_path / "nonexistent.yaml"
    org = lo._ares_normalize(MEDICALC_ARES_RESPONSE)
    ok = lo.apply_to_config(org, cfg, org_index=0, confirm=False)
    assert ok is False
    err = capsys.readouterr().err
    assert "config not found" in err


# ── Provider registry contract ────────────────────────────────────────────


def test_providers_registry_has_cz():
    """ARES provider must be registered under 'CZ'."""
    assert "CZ" in lo.PROVIDERS
    assert callable(lo.PROVIDERS["CZ"])


def test_providers_registry_supports_extension():
    """Registry is mutable so future providers can be added."""
    fake_provider = lambda **kw: []  # noqa: E731
    lo.PROVIDERS["XX"] = fake_provider
    try:
        assert "XX" in lo.PROVIDERS
        results = lo.lookup_org(country="XX", id_="123")
        assert results == []
    finally:
        del lo.PROVIDERS["XX"]
