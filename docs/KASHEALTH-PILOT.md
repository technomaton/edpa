# Kashealth Pilot Kickoff — Medical Platform + Datový e-shop

- **Grant:** CZ.01.01.01/01/24_062/0007440 · OP TAK
- **Org:** [`kashealth`](https://github.com/kashealth) (ČVUT FBMI + Medicalc software s.r.o.)
- **Primary repo:** `kashealth/kas-platform-v1` (private monorepo)
- **EDPA version:** **1.9.0-beta** (release tag, asset `edpa-plugin.tar.gz`)
- **Pilot lead:** Jaroslav Urbánek (Lead Architect / Vedoucí VaV)
- **Pilot kickoff:** 2026-05-07 (proposed)
- **Pilot duration:** 1 PI (5 weeks, target close 2026-06-11)

> Tento dokument je _runbook_ — sekvenční seznam reálných příkazů od
> prázdného repa po uzavřenou iteraci s reporty. Sekce 1–3 jsou
> pre-flight (org-level Issue Types + people.yaml + backlog seed).
> Sekce 4 je `project_setup.py`. Sekce 5–9 vedou prvním PI cyklem,
> sekce 6.5 řeší per-iteration capacity overrides (PTO / sick / IP
> crunch). Sekce 10–11 řeší předvídatelnost (A/B simple vs gates) a
> rollback.

## 0. Quick orientation

Pilot ověří, že EDPA produkuje audit-grade per-person hodiny **z reálné delivery evidence projektu kas-platform-v1**, bez timesheetů. Cílový stav po PI close:

- ✅ GitHub Project `Kashealth-PI-2026-2` s naplněnou hierarchií Initiative → Epic → Feature → Story
- ✅ Per-person `timesheet-<id>.md` pro 4 členy (jurby, turyna, matousek, tuma)
- ✅ `item-costs.xlsx` per-item alokace (sloupce: item, person, role, cw, derived_hours, hourly_rate, cost)
- ✅ Frozen snapshot `PI-2026-2.json` se signature + frozen_at
- ✅ A/B porovnání: `--mode simple` (audit conservative) vs `--mode gates` (default), MAD ≤ 15 % vůči manuálnímu odhadu PM-a
- ✅ Per-iteration capacity overrides ošetřeny pro IP iteraci (PI-2026-2.5) i ad-hoc PTO/sick napříč PI — viz § 6.5

## 1. Pre-flight checklist (před prvním commitem)

**Stav 2026-05-06 (auto-detected):**

| # | Co | Stav | Akce |
|---|----|------|------|
| 1 | Org access (jurby) | ✅ | scopes `admin:org`, `project`, `repo`, `workflow` přítomny |
| 2 | 4 org members | ✅ | `jurby`, `martinturyna`, `dmatousek22`, `sirTurbisCZ` |
| 3 | 3 repos | ✅ | `kas-platform-v1`, `secure-llm-gateway-v1`, `.github` |
| 4 | Org Issue Types: Task + Feature | ✅ | již existují |
| 5 | Org Issue Types: Initiative + Epic + Story + Defect | ⚠ | **chybí — § 1.1** |
| 6 | GitHub Projects | ❌ | žádný — vytvoří § 4 |
| 7 | EDPA plugin v `kas-platform-v1` | ❌ | viz § 2 |
| 8 | `.edpa/config/` naplněný | ❌ | viz § 3 |

### 1.1 Vytvořit chybějící Issue Types v org (jednorázově, idempotentně)

```bash
# DRY-RUN první (vidíte co se vytvoří, žádná mutace)
python3 plugin/edpa/scripts/issue_types.py setup --org kashealth --dry-run

# Reálný setup
python3 plugin/edpa/scripts/issue_types.py setup --org kashealth
```

**Pass:** výstup `✓ All EDPA issue types already configured` nebo `✓ Created Initiative/Epic/Story/Defect`. Podruhé je no-op.

### 1.2 Validace: spuštění preflight skriptu

```bash
sh /Users/jurby/projects/edpa/docs/kashealth-pilot/preflight.sh
```

Vrací **exit 0** když je všechno připravené pro § 2; jinak vypíše seznam chybějících položek + jak je opravit.

## 2. Instalace EDPA pluginu do kas-platform-v1

```bash
# v lokálním klonu kashealth/kas-platform-v1
cd ~/projects/kas-platform-v1   # nebo kdekoli máte klon

# Plugin se stáhne z release v1.9.0-beta tarballu
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

**Očekávaný výstup:** `EDPA 1.9.0-beta installed successfully!` + 3 config soubory ze šablon vytvořeny v `.edpa/config/`.

## 3. Naplnit configy (people.yaml, edpa.yaml)

Skopírujte připravené šablony a edituji jen FTE / capacity / email per člena:

```bash
cp /Users/jurby/projects/edpa/docs/kashealth-pilot/people.yaml.example .edpa/config/people.yaml
cp /Users/jurby/projects/edpa/docs/kashealth-pilot/edpa.yaml.example  .edpa/config/edpa.yaml

# Edituj people.yaml — vyplň FTE, capacity_per_iteration, email per člena
$EDITOR .edpa/config/people.yaml

# Vyplň hourly_rate per role (CZK/h) v people.yaml — pro item-costs.xlsx
# Doporučené (subdoporučení dle governance-reseni-v3.md):
#   Arch:        2400 Kč/h
#   Dev:         1800 Kč/h
#   DevSecOps:   2000 Kč/h
#   QA:          1400 Kč/h
#   PM:          2200 Kč/h
```

**Commit configů hned po editaci** (chrání před § 4 mutace ztracením):

```bash
git add .edpa/config/
git commit -m "EDPA pilot: seed people.yaml + edpa.yaml"
```

## 4. Vytvořit GitHub Project (project_setup.py)

```bash
python3 .claude/edpa/scripts/project_setup.py \
  --org kashealth --repo kas-platform-v1 \
  --project-title "Kashealth-PI-2026-2"
```

**Co se stane:**

1. Lookup existujícího projectu se stejným title (idempotent, v1.8.1+)
2. Pokud nenalezen, vytvoří GitHub Project v2
3. Přidá 21 polí (5 typed Status fields, JS, BV, TC, RR, WSJF, Team, Iteration, …)
4. Přidá repo `kas-platform-v1` jako linked repo
5. Vytvoří 0 issues (zatím prázdný backlog) nebo migruje existující
6. Bootstrap `.edpa/iterations/PI-2026-2.{1..5}.yaml` z cadence (1-week × 5)
7. **STEP 9b auto-commit** stavu (`EDPA: persist setup state for project #N`)

**Pass kritéria po setupu:**

```bash
# Field IDs persistované
yq '.sync.field_ids | keys' .edpa/config/edpa.yaml
# Musí obsahovat: Initiative Status, Epic Status, Feature Status, Story Status, Iteration

# Iteration files vytvořené
ls .edpa/iterations/
# PI-2026-2.yaml + PI-2026-2.{1..5}.yaml

# Setup state je v gitu (NE jen v working tree)
git log --oneline -5
# Musí ukázat: "EDPA: persist setup state for project #N"
```

**Pokud setup skončí s `[failed: typed Status fields missing]`:** GitHub eventual consistency. Spusť `python3 .claude/edpa/scripts/sync.py setup-refresh` (max 19s retry) a setup znovu.

## 5. Naplnit počáteční backlog

První PI typicky obsahuje:

- 1 Initiative (např. `I-1: Medical Platform MVP`)
- 2–3 Epics (např. `E-1: OMOP datový e-shop`, `E-2: Anonymizační pipeline`)
- 4–6 Features (1–2 per Epic)
- 8–12 Stories (per first delivery iteration PI-2026-2.1)

Použijte `backlog.py` pro vytvoření per-item:

```bash
# Příklad — nová Initiative
python3 .claude/edpa/scripts/backlog.py add Initiative "Medical Platform MVP" \
  --js 0 --status Funnel

# Epic pod Initiative
python3 .claude/edpa/scripts/backlog.py add Epic "OMOP datový e-shop" \
  --parent I-1 --js 21 --bv 13 --tc 8 --rr 5 --status Funnel

# Story pod Feature s contributors v as: schemou
python3 .claude/edpa/scripts/backlog.py add Story "Implement OMOP parser" \
  --parent F-1 --js 5 --status Backlog --iteration PI-2026-2.1 \
  --contributor turyna:owner:0.7 \
  --contributor matousek:reviewer:0.3
```

Validace + push do GH Project:

```bash
# Schema check (rejects role:/weight: legacy, requires as:/cw:)
python3 .claude/edpa/scripts/validate_syntax.py --strict .edpa/backlog/

# Push do GitHub Project (vytvoří issues, nastaví field hodnoty)
python3 .claude/edpa/scripts/sync.py push
# → auto-commits issue_map.yaml updates (v1.8.1+)
```

## 6. Práce v PI (5 týdnů)

Tým pracuje normálně — `feature/<item-id>-<description>` branche, PR review, merge. Status changes na backlogu se commitují jako sync commits:

```bash
# Příklad: S-200 přechází do Implementing
yq -i '.status = "Implementing"' .edpa/backlog/stories/S-200.yaml
git commit -m "sync: S-200 Backlog -> Implementing"

# Nebo přes GH UI a pak pull
python3 .claude/edpa/scripts/sync.py pull --commit
# → vytvoří commit "sync: pull N changes from GitHub Projects"
```

**Auto-detection contributorů z PR mergů** je řízeno `.github/workflows/contributor-detect.yml` — po každém merge se přidají `as: key` (PR author) a `as: reviewer` (commit authors / reviewers) do backlog YAMLů.

## 6.5 Per-iteration capacity overrides (v1.9.0+)

`people.yaml` deklaruje **stálou** capacity per člena. Reálné iterace
mají odchylky: dovolená, nemoc, IP crunch, onboarding ramp. Místo
editace `people.yaml` před close + revert (špinavá historie) nebo
multi-contract entries (rozbije reporting) deklaruj override **přímo
v iteration YAML**:

```yaml
# .edpa/iterations/PI-2026-2.5.yaml — IP iterace
iteration:
  id: PI-2026-2.5
  pi: PI-2026-2
  type: ip
  sequence: 5
  start_date: 2026-06-08
  end_date: 2026-06-14
  status: closed

# Iteration-level people overrides — reuse people.yaml schema, partial.
# Engine matchne podle `id` a aplikuje recognised pole
# (capacity_per_iteration). `note:` je volitelný audit annotation.
people:
  - id: turyna
    capacity_per_iteration: 44
    note: "IP weekend deploy push (Jun 13-14, +4h overtime)"
  - id: jurby
    capacity_per_iteration: 10
    note: "vacation Jun 9-11 (3 days PTO certified)"
  - id: matousek
    capacity_per_iteration: 24
    note: "flu Jun 10-12 (sick leave certified)"
  # tuma neposiluje — používá baseline z people.yaml
```

**Engine output:**

```
EDPA 1.9.0-beta — Iteration PI-2026-2.5 (gates mode)
======================================================================
Person                    Role     Capacity  Derived  Items   OK
----------------------------------------------------------------------
J. Urbanek (PTO)          Arch         10.0h    10.0h      2   OK
Turyna (overtime)         Dev          44.0h    44.0h      6   OK
Matousek (sick)           Dev          24.0h    24.0h      3   OK
Tuma                      DevSecOps      40h    40.0h      5   OK
----------------------------------------------------------------------
TEAM TOTAL                            118.0h   118.0h
PLANNING CAPACITY                      94.4h  (factor: 0.8)
```

**Per-person timesheet** ukazuje baseline + override + reason:

```markdown
- Capacity: **44.0h** (baseline 40h, override abs 44h
  (+4h vs baseline 40h) ("IP weekend deploy push (Jun 13-14, +4h overtime)"))
```

**Audit trail v gitu + snapshot:**

- Override commit hint: `git commit -m "PI-2026-2.5: capacity overrides for IP push + 2 PTO/sick"`
- Snapshot drží `capacity_baseline` + `capacity_override.{capacity, note}` per osobu — auditor vidí původní deklaraci i adjustment.
- `validate_syntax.py` blokuje typo (neznámý `id`, duplicitní entry, žádné override fields ani note, negativní capacity).

**Kdy override použít:**

| Scénář | Použití | `capacity_per_iteration` | `note:` |
|--------|---------|--------------------------|---------|
| Vacation (3 dny) | běžné | 10 (z 20) nebo 28 (z 40) | `"vacation Jun 9-11"` |
| Sick leave (2 dny) | občasné | 24 (z 40) | `"flu Jun 10-12 (cert)"` |
| IP crunch | jednou za PI | 44 (z 40) | `"IP weekend deploy push"` |
| Onboarding ramp | jednorázové | 8 → 16 → 24 → 32 → 40 přes 5 iterací | `"onboarding week N"` |
| Plné PTO (celý týden) | občasné | 0 | `"vacation full week"` |
| Audit-only (žádná změna capacity) | dle potřeby | (vypustit pole) | `"pulled in C-suite reviews"` |

> Override `capacity_per_iteration: 0` je validní — osoba má 0 h
> derived hours v této iteraci, invariant zůstane OK pokud nejsou
> kreditové stories. Pokud má kredity ale 0 h capacity, invariant_ok
> bude `false` (audit anomaly — řeší retro).

## 7. Iterační close (po 1 týdnu)

Pro každou delivery iteraci PI-2026-2.{1..4}:

> **Před spuštěním engine:** zkontroluj `.edpa/iterations/PI-2026-2.X.yaml`
> a doplň `people:` overrides pokud někdo z týmu měl odlišnou capacity
> v této iteraci (PTO, sick, overtime). Detail viz § 6.5.

```bash
# 7.0 Volitelně: zaktualizuj iteration YAML o overrides (PTO/sick/overtime)
$EDITOR .edpa/iterations/PI-2026-2.X.yaml
git -c user.email=... add . && git commit -m "PI-2026-2.X: capacity overrides"

# 7.1 Spustit engine v gates mode (default)
python3 .claude/edpa/scripts/engine.py \
  --edpa-root .edpa --iteration PI-2026-2.1 \
  --mode gates \
  --output .edpa/reports/iteration-PI-2026-2.1/edpa_results.json

# 7.2 Vyrobit timesheets + team rollup (deterministicky, žádný Claude)
python3 .claude/edpa/scripts/reports.py PI-2026-2.1
```

**Pass kritéria:**

- `All invariants passed: YES` (per-osobu Σ derived_hours = capacity)
- Snapshot `.edpa/snapshots/PI-2026-2.1.json` má `frozen_at` populated
- 4 timesheet-`<id>`.md soubory + `timesheet-team.md` + `item-costs.xlsx`

## 8. PI close (po 5 týdnech)

```bash
# 8.1 Engine na celý PI
python3 .claude/edpa/scripts/engine.py \
  --edpa-root .edpa --iteration PI-2026-2 \
  --mode gates --output .edpa/reports/iteration-PI-2026-2/edpa_results.json

# 8.2 PI summary aggreguje 4 delivery iterace
python3 .claude/edpa/scripts/reports.py --pi PI-2026-2

# 8.3 BankID podpis snapshotu (audit-grade — volitelné v pilotu)
# Detail v docs/audit-trail.md
```

## 9. A/B parallel: simple vs gates (předvídatelnost)

První PI **paralelně** počítej oba módy. Cíl: validovat, že gates output dává smysl proti manual-baseline od PM-a.

```bash
# Parallel A/B
python3 .claude/edpa/scripts/engine.py --iteration PI-2026-2.1 --mode simple \
  --output .edpa/reports/iteration-PI-2026-2.1/edpa_results_simple.json
python3 .claude/edpa/scripts/engine.py --iteration PI-2026-2.1 --mode gates \
  --output .edpa/reports/iteration-PI-2026-2.1/edpa_results_gates.json

# Diff per-osobu
python3 -c "
import json
s=json.load(open('.edpa/reports/iteration-PI-2026-2.1/edpa_results_simple.json'))
g=json.load(open('.edpa/reports/iteration-PI-2026-2.1/edpa_results_gates.json'))
print(f'{\"Person\":20} {\"Role\":10} {\"simple\":>8} {\"gates\":>8} {\"Δ\":>8}')
for sp, gp in zip(s['people'], g['people']):
    delta = gp['total_derived'] - sp['total_derived']
    print(f'{sp[\"name\"]:20} {sp[\"role\"]:10} {sp[\"total_derived\"]:8.1f} {gp[\"total_derived\"]:8.1f} {delta:+8.1f}')
"
```

**Acceptance:**

| Check | Cílová hodnota |
|-------|----------------|
| Žádná osoba `gates` < `simple` | gates může jen přidat prep credit |
| MAD vůči PM odhadu (per osoba) | ≤ 15 % v 1. PI |
| Σ team derived_hours | == Σ capacity (invariant) |

Po review: rozhodnutí, jestli přepnout default na `gates` pro PI-2026-3, nebo zůstat na `simple` a kalibrovat heuristics později.

## 10. Risk register + rollback

| Risk | Pravděpodobnost | Impact | Mitigace |
|------|-----------------|--------|----------|
| Tým nemá `git config user.email` set | M | sync push auto-commit failne, state v worktree | preflight.sh kontroluje; instrukce `git config --global user.email …` |
| Někdo měl PTO/sick a engine to nezohlednil | M | per-osobu capacity neodpovídá realitě | doplnit `people:` override do iteration YAML před close (§ 6.5); validator hlídá typo, snapshot drží reason v `note:` |
| Iteration field nemá option `PI-2026-2.x` po setup | L | sync push selže `no option_id for Iteration:…` | v1.8.1+ collects ze všech iteration files; pokud chybí, `sync.py add-iteration PI-2026-2.x` |
| Story má `as: developer` (legacy schema) | L | `validate_syntax --strict` ERROR | `migrate_contributors.py` rewrite |
| Member nemá GH login v `people.yaml` | M | evidence detection mine ho | preflight.sh kontroluje email a github fields |
| Engine vrací 0h | L | gates evidence prázdná | engine WARN výpis ukáže `0 evidence pairs derived` + breadcrumb |
| GH Project ručně přejmenován | L | idempotent setup vytvoří duplikát | exact title match — proto přesně `Kashealth-PI-2026-2` |
| Org member ruším z org | M | sync_collaborators.py jej přepne na `availability: unavailable` | týdenní `python3 .claude/edpa/scripts/sync_collaborators.py` |

**Rollback plan:**

- Pilot může být kdykoli stoplý smazáním GH Projectu (`gh project delete N --owner kashealth`) — repo + `.edpa/` zůstávají, žádné side-effect mimo Project.
- Pokud `engine` nevrátí očekávané výsledky, run v `--mode simple` poskytne audit-conservative fallback (jen Done items, žádné gates).
- `git revert` na auto-commit setup state vrátí pre-setup edpa.yaml — ale ID v GH Projectu zůstanou; lépe použít `sync.py setup-refresh` pro re-sync.

## 11. Success criteria — pilot je úspěšný, pokud

| # | Kritérium | Měření |
|---|-----------|--------|
| 1 | EDPA produkuje per-person timesheety pro všechny 4 členy s Σ = capacity | `python3 reports.py PI-2026-2` + manual review |
| 2 | item-costs.xlsx je akceptovatelný pro audit (CZK/h × DerivedHours = item cost, sum přes team = capacity_cost) | manual cross-check vs governance-reseni-v3.md rates |
| 3 | Gates mode produkuje "rozumné" hodiny vs PM odhad (MAD ≤ 15 %) | A/B diff (§ 9) + PM review |
| 4 | Žádná Layer-1 governance ceremonie nebyla zbytečně přidaná (žádný timesheet, žádný TS-tracking tool) | retro feedback od týmu |
| 5 | Setup → first iteration close trvá ≤ 30 min člověka času (nejen wall-clock) | log time-to-close |
| 6 | Auto-commit feature drží state přes 5+ PR mergů | `git log` ukáže `EDPA:` commits jsou in-place po každém pull |

Pokud 5+ z 6 PASS → pilot úspěšný, pokračuj na PI-2026-3 (full prod) a zveřejni jako case study.

## 12. Day-1 — kompletní sekvence (copy-paste ready)

Při souhlasu týmu se spustí v tomto pořadí:

```bash
# === Pre-flight ===
sh ~/projects/edpa/docs/kashealth-pilot/preflight.sh
python3 ~/projects/edpa/plugin/edpa/scripts/issue_types.py setup --org kashealth

# === Instalace + konfigy ===
cd ~/projects/kas-platform-v1
curl -fsSL https://edpa.technomaton.com/install.sh | sh
cp ~/projects/edpa/docs/kashealth-pilot/people.yaml.example .edpa/config/people.yaml
cp ~/projects/edpa/docs/kashealth-pilot/edpa.yaml.example  .edpa/config/edpa.yaml
$EDITOR .edpa/config/people.yaml          # vyplnit FTE, capacity, email
git add .edpa/config/ && git commit -m "EDPA pilot: seed configs"

# === Setup GitHub Project ===
python3 .claude/edpa/scripts/project_setup.py \
  --org kashealth --repo kas-platform-v1 \
  --project-title "Kashealth-PI-2026-2"
# auto-commit "EDPA: persist setup state" by měl proběhnout

# === Sanity check ===
python3 .claude/edpa/scripts/engine.py --status
python3 .claude/edpa/scripts/validate_syntax.py .edpa/

# Hotovo. Tým může začít plnit backlog (§ 5) a normálně pracovat.
```

## 13. Týdenní kontroly (PI cadence)

Každý pondělí ráno (= cca konec předchozí týdenní iterace):

```bash
# Pull recent GH UI changes
python3 .claude/edpa/scripts/sync.py pull --commit

# Iteration close pro uplynulou iteraci (např. PI-2026-2.1)
python3 .claude/edpa/scripts/engine.py --iteration PI-2026-2.X --mode gates \
  --output .edpa/reports/iteration-PI-2026-2.X/edpa_results.json
python3 .claude/edpa/scripts/reports.py PI-2026-2.X

# Distribuce timesheetů (po review):
git add .edpa/reports/iteration-PI-2026-2.X/ .edpa/snapshots/PI-2026-2.X.json
git commit -m "iteration close: PI-2026-2.X"
```

## 14. Otevřené otázky (pro pre-kickoff sync)

Před prvním spuštěním je třeba se rozhodnout:

1. **PI cadence** — AI-native (1-week × 5) vs SAFe (2-week × 10)? *Default: AI-native, lze přepnout v `people.yaml`.*
2. **FTE distribuce** — 1.0 / 0.5 / 0.25 per člen pro PI-2026-2? *Doporučení v `people.yaml.example`.*
3. **hourly_rate** per role — finální čísla pro item-costs.xlsx
4. **Branding timesheets** — `kashealth.cz` letterhead na MD timesheetech? *Volitelné, post-pilot.*
5. **Calibration timing** — kdy spustit `evaluate_cw.py --check-readiness` (potřeba ≥ 20 ground truth records). *Návrh: po PI-2026-2 close + manual review.*
6. **PTO / sick policy** — kdo zapisuje override do iteration YAML (§ 6.5)? Návrh: každý člen sám commituje vlastní `people:` entry pro iteraci, kde měl PTO/sick (před close); PM/Lead audit-checkne při weekly cadence (§ 13). M365 integrace pro auto-fill z OOO calendaru je v2.x roadmap.
7. **IP iterace overtime** — má team policy "+4h IP push" jako standard, nebo ad-hoc? Pokud standard → override přidat preventivně do bootstrapped `PI-2026-2.5.yaml` při setup (§ 4 step 6); pokud ad-hoc → doplnit dle § 6.5 v týdnu close.

## Příloha A — soubory dodané v tomto pilotním balíčku

| Soubor | Účel |
|--------|------|
| `docs/KASHEALTH-PILOT.md` | (tento runbook) |
| `docs/kashealth-pilot/preflight.sh` | automatizovaný readiness check |
| `docs/kashealth-pilot/people.yaml.example` | šablona s 4 členy + role placeholder |
| `docs/kashealth-pilot/edpa.yaml.example` | šablona s `sync.github_org=kashealth, sync.github_repo=kas-platform-v1` |
| `docs/proposals/per-iteration-capacity-overrides.md` | RFC + design pivot za § 6.5 (override schema, validace, snapshot) |

## Příloha B — odkazy

- Governance design: [`docs/examples/governance-kashealth/governance-reseni-v3.md`](examples/governance-kashealth/governance-reseni-v3.md)
- Methodology: [`docs/methodology.md`](methodology.md) (EDPA 1.9.0-beta spec)
- Per-iteration overrides RFC: [`docs/proposals/per-iteration-capacity-overrides.md`](proposals/per-iteration-capacity-overrides.md)
- v1.9.0 E2E report: [`docs/E2E-REPORT-2026-05-06-v190.md`](E2E-REPORT-2026-05-06-v190.md) — IP iteration override scenario PASS
- E2E test plan: [`docs/E2E-TEST-PLAN.md`](E2E-TEST-PLAN.md) — pilot je § 13 plánu
- Last full E2E: [`docs/E2E-REPORT-2026-05-06-v181.md`](E2E-REPORT-2026-05-06-v181.md) — 20/20 PASS
- CHANGELOG: [`CHANGELOG.md`](../CHANGELOG.md) — v1.9.0-beta release notes
