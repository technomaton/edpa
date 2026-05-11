# Kashealth Pilot Runbook (v1.17.1)

- **Grant:** CZ.01.01.01/01/24_062/0007440 · OP TAK
- **Org:** [`kashealth`](https://github.com/kashealth) (ČVUT FBMI + Medicalc software s.r.o.)
- **Primary repo:** `kashealth/kas-platform-v1` (private monorepo)
- **EDPA version:** **1.17.1-beta** — pin pre-kickoff. Inherits the
  v1.17.0 yaml_edit structural signals (8 types) so progressive
  elaboration on Initiatives / Epics / Features (LBC, benefit
  hypothesis, acceptance criteria, NFRs, risks) is credited
  automatically, plus three read-path bug fixes surfaced by the
  2-PI × 5-iteration E2E rerun on 2026-05-10:
  - **IP-iter gate events** — `load_gate_events` now credits the
    transition's commit author when the parent has no
    `contributors[]` yet (typical for strategic work on Initiatives
    /Epics being progressively elaborated). Without the fix, PI-x.5
    closes derived 0h despite real IP work; sandbox went 0h → 120h.
  - **Defect filter** — Defects (and Tasks) now exact-match the
    `iteration:` field like Stories. Before, a Defect with
    `iteration: PI-2026-2.4` was credited in BOTH iter 4 and iter 5,
    doubling its hours in the PI rollup.
  - **`backlog.py tree`/`status`** read project metadata from
    `edpa.yaml` instead of `people.yaml` and tolerate missing keys —
    no more `KeyError: 'project'` on the canonical pilot template.
  No CW recalibration, no schema migration. Single calculation path
  inherited from 1.14; gates + yaml_edit + Done credit converge
  through the same per-item normalization.
- **Pilot lead:** Jaroslav Urbánek (Lead Architect / Vedoucí VaV)
- **Pilot kickoff:** 2026-05-07
- **Pilot duration:** 1 PI (5 weeks, target close 2026-06-11)

## 0. Quick orientation

Pilot ověří, že EDPA produkuje audit-grade per-person hodiny **z reálné delivery evidence projektu kas-platform-v1**, bez timesheetů. Cílový stav po PI close:

- ✅ GitHub Project `Kashealth-PI-2026-1` s naplněnou hierarchií Initiative → Epic → Feature → Story
- ✅ Per-person `timesheet-<id>.md` pro 4 členy
- ✅ Single `edpa-results.xlsx` per iteration (Team Summary + Item Costs tabs)
- ✅ Frozen snapshot `iteration-PI-2026-1.<n>.json` se signature + frozen_at
- ✅ MAD ≤ 15 % engine-output vs manuální odhad PM-a (v1.14+ má jediný calculation path; mode selector dropnut)
- ✅ Per-iteration capacity overrides ošetřeny pro IP iteraci (PI-2026-1.5) i ad-hoc PTO/sick

## 1. Day-1 setup

Tři kroky. `/edpa:setup` Stage 0 (preflight + Issue Types + git config)
běží automaticky; cryptic-GraphQL-error path je odstraněna.

```bash
# 1. Standalone preflight (volitelné, "je projekt ready?"):
python3 .claude/edpa/scripts/project_setup.py \
  --org kashealth --repo kas-platform-v1 --check-only

# 2. Instalace + configy:
cd ~/projects/kas-platform-v1
curl -fsSL https://edpa.technomaton.com/install.sh | sh
cp ~/projects/edpa/docs/kashealth-pilot/people.yaml.example .edpa/config/people.yaml
$EDITOR .edpa/config/people.yaml          # FTE, capacity, email per člena
git add .edpa/config/ && git commit -m "EDPA pilot: seed configs"

# 3. Setup (Stage 0 preflight + provisioning):
python3 .claude/edpa/scripts/project_setup.py \
  --org kashealth --repo kas-platform-v1 \
  --project-title "Kashealth-PI-2026-1"
```

**Stage 0 kontroluje:** `gh` scopes (admin:org, project, repo,
workflow), org access, member presence, Issue Types (Initiative, Epic,
Feature, Story, Defect, Task), `git config user.email`, Python ≥ 3.10
+ `yaml` + `openpyxl`. Failures nabízí auto-fix s explicitním
potvrzením. Issue Types missing → nabídne `issue_types.py setup --org`.

**Pokud chce CI / scripted run:** přidej `--non-interactive --auto-fix`.

## 2. Naplnit počáteční backlog

```bash
python3 .claude/edpa/scripts/backlog.py add Initiative "Medical Platform MVP" --js 0
python3 .claude/edpa/scripts/backlog.py add Epic "OMOP datový e-shop" --parent I-1 --js 21 --status Funnel
python3 .claude/edpa/scripts/backlog.py add Story "Implement OMOP parser" \
  --parent F-1 --js 5 --iteration PI-2026-1.1 \
  --contributor turyna:owner:0.7 --contributor matousek:reviewer:0.3

python3 .claude/edpa/scripts/validate_syntax.py --strict .edpa/backlog/
python3 .claude/edpa/scripts/sync.py push
```

První PI typicky: 1 Initiative, 2–3 Epics, 4–6 Features, 8–12 Stories
napříč PI-2026-1.{1..4}.

## 3. Weekly cadence

Každé pondělí ráno (= konec předchozí týdenní iterace):

```bash
# Pull GH UI changes
python3 .claude/edpa/scripts/sync.py pull --commit

# Close uplynulou iteraci (prep + engine + reports)
/edpa:close-iteration PI-2026-1.X
```

`/edpa:close-iteration` má tři formy:

| Forma | Co dělá |
|-------|---------|
| `<iter>` | Full close: prep prompt (capacity overrides) → engine → reports |
| `<iter> --prep-only` | Jen prep: zaznamená override, necommitne engine. Pro mid-iteration recording (PTO oznámí v úterý, close je v pátek). |
| `<iter> --skip-prep` | Engine + reports bez prep promptu. Pro re-run / scripted close. |

Stage 1 (prep) interaktivně zeptá *"Did anyone have non-baseline
capacity?"* a volá `capacity_override.py --add` per osobu. Validuje
proti people.yaml, computes diff vs baseline, prompts for audit note,
auto-commits s `<iter>: capacity override <person> -> <hours>h
(<note>)`. Closed iterations odmítnou override.

Stage 2 spustí `edpa-engine` → `edpa-reports`. Engine vyrobí
`edpa_results.json` + `edpa-results.xlsx` (Team Summary + Item Costs
tabs). Reports vyrobí `timesheet-<id>.md` per osobu + `timesheet-team.md`
+ frozen snapshot `iteration-<id>.json`.

## 4. PI close (po 5 týdnech)

```bash
/edpa:close-iteration PI-2026-1
```

(Bez `.<n>` suffix — close PI-level rollup. Stage 1 prep se přeskočí
automaticky, overrides žijí na per-iteration files.)

BankID podpis snapshotu je audit-grade volitelná, viz
`docs/audit-trail.md`.

## 5. Edge cases

### 5.1 Capacity overrides — kdy a jak

| Scénář | Forma | Hours | Note |
|--------|-------|-------|------|
| Vacation 3 dny | `--add` | `-12` (delta) nebo `28` (abs) | `"vacation Jun 9-11"` |
| Sick leave 2 dny | `--add` | `-16` | `"flu Jun 10-12 (cert)"` |
| IP crunch +4 h | `--add` | `+4` | `"IP weekend deploy push"` |
| Onboarding ramp | `--add` | abs (8 → 16 → 24 → ...) | `"onboarding week N"` |
| Plné PTO (celý týden) | `--add` | `0` | `"vacation full week"` |
| Audit-only (žádná změna) | `--add` | (vypustit `--hours`) | `"context note"` |

Mid-iteration recording (PTO oznámí v úterý, close je v pátek):

```bash
python3 .claude/edpa/scripts/capacity_override.py PI-2026-1.3 \
  --add --person urbanek --hours 16 --note "vacation Jun 9-11 (3 dny PTO cert)"
```

Standalone `--list` / `--remove` viz `--help`.

### 5.2 MAD validation vs PM ground truth

Mode selector (`--mode simple|gates`) byl odebrán v 1.14 — jediný
calculation path teď konverguje přes Story/Defect Done credit + gate
events + (v1.17) yaml_edit signals. PI-1 close porovnej engine output
s manuálním PM odhadem:

```bash
# Engine spuštěný přes /edpa:close-iteration vyrobí kanonický výstup
python3 .claude/edpa/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.1 \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json

# PM napíše per-person odhad ručně (gut estimate) do PI close retro;
# evaluate_cw.py spočítá MAD proti seedovaným contributors[].cw
python3 .claude/edpa/scripts/evaluate_cw.py --iteration PI-2026-1.1 \
  --ground-truth .edpa/reports/pm-baseline-PI-2026-1.1.yaml
```

Acceptance: MAD ≤ 15 % vůči PM gut estimate; **Σ team derived ≤ Σ
capacity** (per-person rule `derived ≤ cap`, ne tvrdá rovnost — IP
iter může mít víc strategie/přípravy než delivery, vyšlí se přes
yaml_edit signaly automaticky).

### 5.3 Rollback

- Pilot lze stoplý smazáním GH Projectu (`gh project delete N --owner kashealth`); repo + `.edpa/` zůstávají.
- Engine warns `0 evidence pairs` → ověř, že `.edpa/backlog/` má seedované Stories s `iteration:` polem a status=Done; v1.17 yaml_edit signals naběhnou automaticky pokud jsou commits ve window.
- Setup `--check-only` můžeš spustit kdykoli pro re-validation.

## 6. Success criteria

| # | Kritérium | Měření |
|---|-----------|--------|
| 1 | EDPA produkuje per-person timesheety pro všechny 4 členy s Σ = capacity | reports + manual review |
| 2 | `edpa-results.xlsx` (Team Summary + Item Costs tabs) je akceptovatelný pro audit | manual cross-check vs governance-reseni-v3.md rates |
| 3 | Gates mode produkuje "rozumné" hodiny vs PM odhad (MAD ≤ 15 %) | A/B diff (§ 5.2) + PM review |
| 4 | Žádná Layer-1 governance ceremonie nebyla zbytečně přidaná (žádný timesheet, žádný TS-tracking tool) | retro feedback od týmu |
| 5 | Setup → first iteration close ≤ 30 min člověka času | log time-to-close |
| 6 | Auto-commit feature drží state přes 5+ PR mergů | `git log` ukáže `EDPA:` commits in-place po každém pull |

Pokud 5+ z 6 PASS → pilot úspěšný, pokračuj na PI-2026-2 (full prod) a zveřejni jako case study.

## 7. Open questions (pre-kickoff sync)

1. **PI cadence** — 1-week × 5 (default) vs 2-week × 5? Nastavitelné v `people.yaml`.
2. **FTE distribuce** — 1.0 / 0.5 / 0.25 per člen? Doporučení v `people.yaml.example`.
3. **Cost reporting** — sazby drží **privátní registr** (ne EDPA people.yaml). Auditor format = open question.
4. **Calibration timing** — `evaluate_cw.py --check-readiness` po PI-2026-1 close (potřeba ≥ 20 ground truth records).
5. **PTO / sick policy** — kdo zapisuje override? Návrh: každý člen sám commituje vlastní entry před close; PM/Lead audit-checkne weekly.
6. **IP iterace overtime** — standard "+4h IP push", nebo ad-hoc? Pokud standard → preventivně override v PI-2026-1.5.

## 8. Reference

- Methodology: [`docs/methodology.md`](../methodology.md) (EDPA 1.17.1-beta spec)
- v1.17.1 E2E validation: `CHANGELOG.md` § 1.17.1-beta — three bugs found by 2-PI × 5-iter rerun, all fixed pre-kickoff
- v1.17 yaml_edit calibration corpus: [`docs/proposals/v1.17-yaml-edit-calibration-corpus.md`](../proposals/v1.17-yaml-edit-calibration-corpus.md) — pre-Monte Carlo edge case memo
- v1.10 RFC: [`docs/proposals/v1.10-skill-first-gaps-and-excel-consolidation.md`](../proposals/v1.10-skill-first-gaps-and-excel-consolidation.md)
- v1.9.0 capacity overrides RFC: [`docs/proposals/per-iteration-capacity-overrides.md`](../proposals/per-iteration-capacity-overrides.md)
- E2E test plan: [`docs/E2E-TEST-PLAN.md`](../E2E-TEST-PLAN.md)
- CHANGELOG: [`CHANGELOG.md`](../../CHANGELOG.md)
- Governance design: [`docs/examples/governance-kashealth/governance-reseni-v3.md`](../examples/governance-kashealth/governance-reseni-v3.md)
