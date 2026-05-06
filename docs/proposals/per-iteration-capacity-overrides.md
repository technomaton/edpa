# RFC — Per-person, per-iteration capacity overrides

- **Status:** **implemented in v1.9.0-beta** (with schema pivot — see § 13)
- **Author:** Jaroslav Urbánek (proposal request 2026-05-06)
- **Target release:** v1.9.0-beta
- **Required for:** kashealth pilot (IP iteration with crunch hours expected)
- **Effort estimate:** ~80 lines code + ~60 lines tests, 1 dev-day

## 1. Problem statement

`people[].capacity_per_iteration` v `people.yaml` je **konstantní napříč
všemi iteracemi**. EDPA garantuje `Σ DerivedHours[person] = capacity[person]`
jako tvrdý invariant. Pokud má reálná osoba v jedné konkrétní iteraci
**jinou kapacitu** než ostatní, není dnes čistá cesta to vyjádřit:

| Scénář | Frekvence | Důvod změny capacity |
|--------|-----------|----------------------|
| Vacation / sick / PTO | běžné | minus 8–40 h v jedné iteraci |
| Crunch / IP push / hackathon | občasné | plus 4–16 h v jedné iteraci |
| Onboarding / offboarding | jednorázové | ramp 25 % → 100 % přes 2-3 iterace |
| Mateřská / rodičovská | jednorázové | 100 % → 0 % na ≥6 PI |
| Půl-iterace (sub-week) | občasné | bob jel v pondělí a úterý, pak nemoc |

**Současné workaroundy:**

- **A** — editovat `people.yaml.capacity_per_iteration` před `engine` close,
  commit, run, revert. Funguje, ale git historie zašpiní (3 commity místo 1)
  a okno mezi editací a `revert` riskuje, že někdo pull-ne mezizákazem.
- **B** — multi-contract entry per osoba (`bob-dev-baseline` + `bob-dev-overtime`).
  Funguje, ale rozbije reporting (osoba vystupuje jako 2 lidi v
  timesheet-team.md), porušuje 1:1 mapping na GitHub login a komplikuje
  evidence detekci (commit author == bob → který kontrakt?).

**Co nelze řešit současnými prostředky:** říct engineu "bob má v
PI-2026-1.3 navíc 4 h, ale zůstává jednou osobou v reportu se signaturou
git/GH = `jurby`".

## 2. Cílový tvar pro uživatele

Vstup do iteration YAML:

```yaml
# .edpa/iterations/PI-2026-1.3.yaml
iteration:
  id: PI-2026-1.3
  pi: PI-2026-1
  type: ip                 # delivery | ip
  sequence: 5
  start_date: 2026-06-08
  end_date: 2026-06-14
  status: closed

# NEW (v1.9.0-beta): per-person capacity overrides for THIS iteration only.
capacity_overrides:
  - person: bob-dev
    delta: +4              # 40 h baseline + 4 h overtime → 44 h
    reason: "IP weekend deploy push (Jun 13–14)"
  - person: alice-arch
    absolute: 10           # half iteration (10 h místo 20 h)
    reason: "vacation Jun 9–11 (3 dny PTO)"
  - person: carol-qa
    delta: -16             # nemoc, 30 h baseline - 16 h → 14 h
    reason: "flu Jun 10–12 (sick leave certified)"
```

Engine output (CLI):

```
EDPA 1.9.0-beta — Iteration PI-2026-1.3 (gates mode)
======================================================================
Person                    Role     Capacity  Derived  Items   OK
----------------------------------------------------------------------
Alice Architect (PTO)     Arch          10h    10.0h      2   OK    ← capacity_override applied: -10h
Bob Developer (overtime)  Dev           44h    44.0h      6   OK    ← capacity_override applied: +4h
Carol QA (sick)           QA            14h    14.0h      1   OK    ← capacity_override applied: -16h
Dave PM                   PM            10h    10.0h      2   OK
----------------------------------------------------------------------
TEAM TOTAL                              78h    78.0h
PLANNING CAPACITY                     62.4h  (factor: 0.8)
```

Snapshot uchovává **baseline + override + reason** pro audit:

```json
{
  "iteration": "PI-2026-1.3",
  "people": [
    {
      "id": "bob-dev",
      "name": "Bob Developer",
      "role": "Dev",
      "capacity": 44,
      "capacity_baseline": 40,
      "capacity_override": {
        "delta": 4,
        "reason": "IP weekend deploy push (Jun 13–14)",
        "applied_at": "2026-06-15T09:00:00+00:00"
      },
      "total_derived": 44.0,
      "invariant_ok": true,
      ...
    }
  ]
}
```

## 3. Schema rules

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `capacity_overrides` | list[map] | no | top-level v iteration YAML, sourozenec `iteration:` |
| `capacity_overrides[].person` | string | yes | musí matchnout `people[].id` v people.yaml |
| `capacity_overrides[].delta` | number | yes XOR `absolute` | hours; integer or float; -X..+X |
| `capacity_overrides[].absolute` | number | yes XOR `delta` | hours ≥ 0 |
| `capacity_overrides[].reason` | string | yes | min 10 chars (audit-grade) |
| `capacity_overrides[].applied_at` | ISO timestamp | no (auto-filled) | engine sets to now() if missing |

**Validace v `validate_syntax.py`:**

- Hard error pokud:
  - `person` neodpovídá `people[].id`
  - oboje `delta` a `absolute` (mutually exclusive)
  - ani `delta` ani `absolute`
  - `absolute < 0`
  - `reason` chybí nebo < 10 chars
  - duplicitní záznam pro stejnou osobu v jedné iteraci
- Warning pokud:
  - `absolute > 2× baseline` (sanity, asi překlep)
  - `baseline + delta < 0` (negativní effective capacity)

## 4. Engine integration

### 4.1 Kde se capacity čte (current state)

`engine.py:220-223` — single point:

```python
for person in people:
    pid = person["id"]
    cpi = person.get("capacity_per_iteration")
    capacity = cpi if cpi is not None else person.get("capacity", 0)
```

### 4.2 Změna (~30 řádků v `engine.py`)

Nový helper `_load_capacity_overrides(edpa_root, iteration_id)`:

```python
def _load_capacity_overrides(edpa_root, iteration_id):
    """Return {person_id: {delta?: float, absolute?: float, reason: str}}.

    Empty dict when iteration has no `capacity_overrides:` section.
    Caller resolves baseline + override at engine runtime.
    """
    if not iteration_id:
        return {}
    iter_file = Path(edpa_root) / "iterations" / f"{iteration_id}.yaml"
    if not iter_file.is_file():
        return {}
    data = yaml.safe_load(iter_file.read_text(encoding="utf-8")) or {}
    overrides = data.get("capacity_overrides") or []
    out = {}
    for entry in overrides:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("person")
        if not pid:
            continue
        out[pid] = {
            "delta": entry.get("delta"),
            "absolute": entry.get("absolute"),
            "reason": entry.get("reason", ""),
        }
    return out


def _resolve_capacity(person, override):
    """Apply override on top of baseline. Returns (effective, baseline, override_meta)."""
    cpi = person.get("capacity_per_iteration")
    baseline = cpi if cpi is not None else person.get("capacity", 0)
    if not override:
        return baseline, baseline, None
    if override.get("absolute") is not None:
        eff = float(override["absolute"])
    else:
        eff = baseline + float(override.get("delta") or 0)
    return eff, baseline, {
        "delta": override.get("delta"),
        "absolute": override.get("absolute"),
        "reason": override.get("reason", ""),
    }
```

V `run_edpa()`:

```python
# was: capacity = cpi if cpi is not None else person.get("capacity", 0)
overrides = _load_capacity_overrides(edpa_root, iteration_id)
for person in people:
    pid = person["id"]
    capacity, baseline, override_meta = _resolve_capacity(person, overrides.get(pid))
    ...
    results.append({
        ...
        "capacity": capacity,
        "capacity_baseline": baseline,
        "capacity_override": override_meta,  # None when no override
        ...
    })
```

### 4.3 Snapshot persist (~10 řádků v `_snapshot_payload`)

`derived_reports[]` přidává `capacity_baseline` a `capacity_override`
fields (oba None když nebylo přepsáno).

### 4.4 Reports (~20 řádků v `reports.py`)

`timesheet-<id>.md` zobrazí baseline + override když přítomno:

```markdown
- Capacity: **44h**
  (baseline 40h + override **+4h**: "IP weekend deploy push (Jun 13–14)")
- Derived: **44.0h**
- Invariant: **OK**
```

`timesheet-team.md` přidává sloupec "Override" když cokoli iterace
má capacity_overrides:

```
| Person | Role | Capacity | Override | Derived | Items |
|--------|------|----------|----------|---------|-------|
| Bob    | Dev  | 44h      | +4h (overtime)  | 44.0h | 6 |
| Alice  | Arch | 10h      | abs 10h (PTO)   | 10.0h | 2 |
| Carol  | QA   | 14h      | -16h (sick)     | 14.0h | 1 |
| Dave   | PM   | 10h      | —               | 10.0h | 2 |
```

`pi-summary-<PI>.md` agreguje "iterations with overrides" sekci.

## 5. Audit trail integrity

| Property | Současný stav | S override |
|----------|---------------|-----------|
| `Σ DerivedHours = Capacity` per person | invariant | invariant zachován (capacity je effective) |
| `team_total = Σ capacity` | invariant | invariant zachován |
| Důvod změny capacity | git log + manual editace people.yaml | strukturovaný `reason:` v iteration YAML |
| Reproducibility | yes | yes (snapshot signature zahrnuje override) |
| Ground-truth pro calibration | per-iteration capacity | beze změny (calibration porovnává CW, ne capacity) |

**Snapshot signature** (`payload_signature` from L1+L6) zahrnuje
override metadata, takže každá změna capacity_override → nová revision.

## 6. Backward compatibility

100 % zachována:

- `capacity_overrides:` je **volitelné** — staré iteration YAMLy projdou beze změny.
- `_resolve_capacity` vrací baseline když override není přítomen — žádný behavior change pro neoverridované osoby.
- `derived_reports[].capacity_baseline` / `capacity_override` jsou **nové fieldy**, staré snapshoty je nemají, reader by měl tolerovat None (`reports.py` ano).
- `validate_syntax.py` v non-strict mode přidává jen warnings na malformed override, ne errors.

## 7. Edge cases

### 7.1 Override pro osobu, která nemá v iteraci žádné kredity

Bob má override `+4h`, ale v PI-2026-1.3 nemá ani jeden Done item ani gate
kredit → effective_capacity = 44 h, derived_hours = 0, invariant_ok = **false**.

**Současné chování engine:** `invariant_ok` je per-osoba flag; engine projde,
report ukáže `0h / 44h capacity, invariant FAIL`. Tým může:
1. Smazat override z iteration YAML (osoba neměla extra hours, nebyl důvod)
2. Připsat osobu jako contributor některé Done story (pokud reálně přispěla)
3. Akceptovat invariant_ok=false jako known anomaly v auditu

### 7.2 Negativní effective capacity

`baseline 30 h + delta -40 h` → effective = -10 h. **Hard error v engine** —
capacity musí být ≥ 0.

### 7.3 Override aplikován retroaktivně

PI je `closed`, snapshot existuje. Operátor přidá override, znovu spustí engine.
- Snapshot se neupravuje (immutable po close), ale engine přepíše
  `_rev2.json` snapshot s novým signature (logický fork).
- `iteration_close` workflow může detekovat změnu po close a:
  - varovat "snapshot exists, applying override creates revision"
  - vyžádat `--force` pro pokračování

### 7.4 Override absolute = baseline

`absolute: 40` při baseline 40 → effective stejné. Engine to akceptuje
(nemá smysl to bránit), reports ukáží "override: abs 40h ≡ baseline".

### 7.5 Override per IP iterace, kde se každý vždy přetížil

Recurring pattern — IP iterace má systematicky víc hodin. Doporučení:
**neperzistovat jako override**, ale jako per-cadence parametr:

```yaml
cadence:
  ip_capacity_factor: 1.1   # IP iter má 1.1× baseline pro celý team
```

Tohle je samostatný RFC (out of scope tady), pokud se ukáže potřeba.

## 8. Implementation plan (v1.9.0-beta)

| File | LoC | Co |
|------|-----|---|
| `plugin/edpa/scripts/engine.py` | +35 | `_load_capacity_overrides`, `_resolve_capacity`, integrace do `run_edpa()` + `_snapshot_payload` |
| `plugin/edpa/scripts/validate_syntax.py` | +40 | `_validate_capacity_overrides()` helper, errors + warnings |
| `plugin/edpa/scripts/reports.py` | +25 | timesheet/team rollup formatters acknowledge override |
| `tests/test_capacity_overrides.py` | +120 | 8 unit testů (per § 7) |
| `docs/methodology.md` | +20 | sekce "Per-iteration capacity adjustments" |
| `CHANGELOG.md` | +12 | v1.9.0-beta entry |
| **Total** | **~250** | 1 dev-day |

Žádné breaking changes → minor bump. Migration script není potřeba.

## 9. Acceptance tests

```python
def test_delta_override_applied(tmp_path):
    """+4h override → effective = baseline + 4."""
    # baseline 40 h, delta +4 → engine outputs 44 h capacity, 44 h derived

def test_absolute_override_applied(tmp_path):
    """absolute=10 → effective = 10 regardless of baseline."""

def test_override_for_unknown_person_fails_validation(tmp_path):
    """capacity_overrides[].person not in people.yaml → validate_syntax ERROR"""

def test_delta_xor_absolute(tmp_path):
    """Both fields set → ERROR; neither → ERROR."""

def test_negative_effective_capacity_rejected(tmp_path):
    """baseline 30 h + delta -40 h → engine raises ValueError."""

def test_snapshot_records_baseline_and_override(tmp_path):
    """JSON snapshot has capacity, capacity_baseline, capacity_override."""

def test_no_override_section_is_no_op(tmp_path):
    """Iteration without capacity_overrides → behavior identical to v1.8.x."""

def test_invariant_holds_with_override(tmp_path):
    """Σ DerivedHours = capacity (effective) per person, even with override."""
```

## 10. Open questions

1. **Override = 0 absolute** (osoba na PTO celou iteraci) → engine projde s 0 h
   capacity, 0 h derived, invariant_ok=true. Akceptovat, nebo zvláštní marker
   `unavailable: true` lépe vyjadřuje záměr?

2. **Overrides v `iterations/PI-X.yaml`** (PI-level) jako wildcard pro všechny
   delivery iterace v PI? Out of scope v1.9.0, ale stojí za zvážení.

3. **Auto-detection z calendaru** (Outlook / Google Calendar OOO) → fill
   `capacity_overrides` automaticky. Out of scope v1.9.0; potenciální v2.x
   feature pro M365-integrated týmy (kashealth má M365).

4. **Per-day capacity** místo per-iteration (Bob jel jen Po-Út, pak nemoc).
   Vysoká granularita → vysoká cena. Doporučuji odložit; pokud reálná
   potřeba, řešit jako sub-feature v2.0.

## 11. Decision

**Doporučuji implementovat jako v1.9.0-beta** před kashealth pilotem
(scheduled 2026-05-07). První IP iterace (PI-2026-2.5) je očekávaný moment,
kdy potřeba vznikne — mít to připravené předem ušetří workarounds A/B.

Pokud schváleno:

1. Implementace dle § 8 (1 dev-day)
2. Tests dle § 9
3. CHANGELOG + bump na v1.9.0-beta
4. Re-run E2E (E2E-REPORT-2026-05-06-v190.md) s capacity_override scénářem
5. Tag + push + release

Pokud zamítnuto: aktualizovat `docs/KASHEALTH-PILOT.md` § 14 o postup A
("editovat people.yaml před close, commit, revert") jako oficiální doporučení
pro pilot a tag tuto RFC jako `status: deferred`.

## 12. Alternativy zvážené

| Alternativa | Pros | Cons | Verdikt |
|-------------|------|------|---------|
| Path A: edit people.yaml + revert | žádný kód | špinavá historie, race condition | již existuje, ne dlouhodobé řešení |
| Path B: multi-contract per osoba | žádný kód | rozbije 1:1 git mapping, infl. reports | pro recurring patterns OK, pro ad-hoc ne |
| **Path C: capacity_overrides v iteration YAML** | čistá historie, audit-grade reason, žádný impact na people.yaml | +250 LoC | **doporučeno** |
| Path D: separate `capacity_overrides.yaml` | symetrické s `heuristics.yaml` | další konfig, méně lokality | overengineering |
| Path E: capacity_factor multiplier | jednoduchost | ztrácí absolutní hodiny | nedostatečné pro PTO |
| Path F: structured calendar events log | flexibilní | komplexní agregace, vyšší LoC | out of scope v1.9 |
| **Path G: iteration-level `people:` override (reuse people.yaml schema)** | **reuse existing schema, žádné nové vocabulary** | **degraduje povinný `reason:` na volitelný `note:`** | **vybráno — implementováno v v1.9.0** |

## 13. Implementation pivot — schema review (post-RFC)

Při review prvního drafu zazněl argument: "místo zavádět nový blok
`capacity_overrides:` s `delta`/`absolute`/`reason` recyklujme
existující `people:` schema z `people.yaml` jako partial override".

### Pivot rationale

| Aspekt | RFC v1 (`capacity_overrides:`) | v1.9.0 final (`iteration.people[]`) |
|--------|-------------------------------|-------------------------------------|
| Vocabulary | nový (`delta`, `absolute`, `reason`) | žádný (reuse `people:`) |
| Semantika | additive (delta) nebo absolute | absolute only (`capacity_per_iteration: 44`) |
| Audit reason | `reason:` povinný (≥10 znaků) | `note:` volitelný |
| Sanity check | reason ≥10 znaků; one-of(delta, absolute) | non-empty entry: capacity nebo note |
| LoC | ~80 v engine + ~75 v validator | ~60 v engine + ~75 v validator |
| Forward compat | jen capacity | celé people schema (availability, fte, …) později |

Trade-off: ztrácíme "audit-grade" sílu povinného `reason:`. Validator
odmítne entry bez capacity i bez note jako "no override fields"
(typo guard). Operator může psát jen `capacity_per_iteration: 44`
bez note — engine to vezme, ale audit log v gitu pak nese kontext
v commit message.

### Final schema

```yaml
# .edpa/iterations/PI-2026-1.3.yaml
iteration:
  id: PI-2026-1.3
  pi: PI-2026-1
  type: ip
  sequence: 5
  start_date: 2026-06-08
  end_date: 2026-06-14
  status: closed

# Iteration-level people overrides (v1.9.0+).
# Reuses .edpa/config/people.yaml schema; engine matches by `id` and
# overrides recognised fields. `note:` is optional audit annotation.
people:
  - id: bob-dev
    capacity_per_iteration: 44
    note: "IP weekend deploy push (Jun 13-14)"
  - id: alice-arch
    capacity_per_iteration: 10
    note: "vacation Jun 9-11 (3 days PTO)"
  - id: carol-qa
    capacity_per_iteration: 14
    note: "flu Jun 10-12 (sick leave certified)"
```

### Engine internals (final)

`_load_iteration_people_overrides()` čte `iteration.people[]` a
vrací `{person_id: full_entry_dict}`. `_resolve_capacity()` matchne
`capacity_per_iteration` (nebo legacy alias `capacity`); ostatní
fields nech prozatím beze změny chování — známka pro budoucí
expansion (override `availability` aj.).

Snapshot zachovává původní strukturu: `capacity_baseline`,
`capacity_override = {capacity, note}` jen když override přitomen,
jinak fields vůbec ne (zachovává L6 dedup byte-identicky).

### Validator (final)

`validate_iteration_people_overrides()` (alias
`validate_capacity_overrides` zachovaný pro backward-compat). Hard
errors na: neznámý id, duplicitní id, missing id, žádné override
fields ani note, negativní capacity. Žádné varování pro >2× baseline
v této verzi (může se přidat ve v1.10.0 pokud je potřeba).

### Test coverage

15 unit testů v `tests/test_capacity_overrides.py` — engine integration
(7), validator (7), snapshot persistence (1).

