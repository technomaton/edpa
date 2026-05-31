# Kashealth Pilot Runbook (v2.1.8)

- **Grant:** CZ.01.01.01/01/24_062/0007440 · OP TAK
- **Org:** [`kashealth`](https://github.com/kashealth) (ČVUT FBMI + Medicalc software s.r.o.)
- **Primary repo:** `kashealth/kas-platform-v1` (private monorepo)
- **EDPA version:** **2.1.8** — pin pre-kickoff. EDPA V2 je
  **local-first**: source of truth je `.edpa/backlog/**/*.md` (Markdown
  s YAML frontmatter), GitHub je **volitelný** (audit trail = git
  historie). Žádné GitHub Project provisioning, žádné org Issue Types,
  žádný bidirectional sync. Engine kredituje delivery z lokální
  evidence (commit authors přes post-commit hook + `/contribute`
  directive) a — pokud je zapnutý `--with-ci` workflow — z PR-thread
  signálů. Single calculation path zděděná z 1.14:
  - **yaml_edit structural signals** — progressive elaboration na
    Initiatives / Epics / Features (LBC, benefit hypothesis, acceptance
    criteria, NFRs, risks) se kredituje automaticky podle commitů nad
    `.edpa/backlog/<typ>/<id>.md` v okně iterace (create / block_add /
    list_grow / scalar_change / lines_volume / contributors_rebalance /
    revert).
  - **Gate events** — Feature/Epic/Initiative status transitions z git
    history kreditují autora commitu transition.
  - **Done credit** — Story/Defect s `iteration:` match a status=Done.
  Všechny tři konvergují přes per-item normalizaci `contributors[].cw`
  (Σ napříč osobami = 1.0 per item).
- **Pilot lead:** Jaroslav Urbánek (Lead Architect / Vedoucí VaV)
- **Pilot kickoff:** 2026-05-07
- **Pilot duration:** 1 PI (5 weeks, target close 2026-06-11)

## 0. Quick orientation

Pilot ověří, že EDPA produkuje audit-grade per-person hodiny **z reálné delivery evidence projektu kas-platform-v1**, bez timesheetů. Cílový stav po PI close:

- ✅ Lokální backlog `.edpa/backlog/**/*.md` s naplněnou hierarchií Initiative → Epic → Feature → Story (git = audit trail)
- ✅ Per-person `timesheet-<id>.md` pro 4 členy
- ✅ Single `edpa-results.xlsx` per iteration (Team Summary + Item Costs tabs)
- ✅ Frozen snapshot `.edpa/snapshots/PI-2026-1.<n>.json` se signature (`payload_signature`) + `frozen_at`
- ✅ MAD ≤ 15 % engine-output vs manuální odhad PM-a (jediný calculation path; mode selector dropnut)
- ✅ Per-iteration capacity overrides ošetřeny pro IP iteraci (PI-2026-1.5) i ad-hoc PTO/sick

## 1. Day-1 setup

Dva kroky, oba **lokální** — žádný GitHub provisioning. `/edpa:setup`
vendorne engine do `.edpa/engine/`, naseedne configy + `id_counters.yaml`
a (s flagy) nainstaluje git hooky, PR-signal CI workflow a `.claude/rules/`.

```bash
cd ~/projects/kas-platform-v1

# 1. Instalace + vendoring + configy + hooky + CI + rules:
#    a) z Claude Code:
/edpa:setup --with-ci --with-hooks --with-rules
#    b) nebo z shellu (non-Claude-Code):
curl -fsSL https://edpa.technomaton.com/install.sh | sh

# 2. Naseedni configy z pilot šablon a vyplň tým:
cp ~/projects/edpa/docs/kashealth-pilot/edpa.yaml.example   .edpa/config/edpa.yaml
cp ~/projects/edpa/docs/kashealth-pilot/people.yaml.example .edpa/config/people.yaml
$EDITOR .edpa/config/people.yaml          # FTE, capacity, email, github per člena
git add .edpa/config/ && git commit -m "chore(edpa): seed configs for pilot"
```

**`project_setup.py` (= `/edpa:setup`) udělá:**
1. **Vendorne engine** (`scripts` + `schemas` + `templates` + `VERSION`)
   do `.edpa/engine/` — aby CI workflow, dokumentované
   `.edpa/engine/scripts/*.py` CLI i non-Claude-Code nástroje resolvovaly.
2. Vytvoří directory tree (`config`, `backlog/*`, `iterations`,
   `reports`, `snapshots`, …).
3. Naseedne `.edpa/config/{edpa.yaml,people.yaml,cw_heuristics.yaml}`
   z `.edpa/engine/templates/*.tmpl` (idempotentně) a stampne
   `governance.methodology` na nainstalovanou verzi.
4. Naseedne `.edpa/config/id_counters.yaml` (local-first ID allocator)
   z existujících file IDs.
5. `--with-ci` → zkopíruje `.github/workflows/edpa-contribution-sync.yml`.
6. `--with-hooks` → nainstaluje git hooky (pre-commit + commit-msg +
   post-commit + pre-push).
7. `--with-rules` → zkopíruje `plugin/rules/*.md` do `.claude/rules/`
   (auto-load do každé Claude Code session v repu).

**Ověření, že je projekt ready** (kdykoli, idempotentně):

```bash
sh ~/projects/edpa/docs/kashealth-pilot/preflight.sh
```

Preflight kontroluje **jen lokální stav**: Python ≥ 3.10 + `pyyaml` +
`openpyxl` (+ `ruamel.yaml`), `git` + `git config user.email`, že
`.edpa/engine/scripts/` je vendorovaný a `.edpa/config/` naseedovaný.
Žádné `gh` scopes, žádný org access, žádné Issue Types — `gh` je
volitelný (jen pro `--with-ci`).

### 1.1 `EDPA_TOKEN` secret — VOLITELNÉ (jen pro PR-signal sync)

V2 nepotřebuje žádný PAT pro chod. Lokální evidence (commit authors přes
post-commit hook + `/contribute @person weight:N` directive) pokrývá
attribution sama o sobě. **Jediný** workflow, který GitHub token používá,
je volitelný `--with-ci` job:

- **`edpa-contribution-sync.yml`** → `sync_pr_contributions.py` —
  materializuje PR-thread signály (pr_author / pr_reviewer /
  issue_comment) do `evidence[]` backlog items. Tyhle signály jsou
  *PR-thread-only* (default `GITHUB_TOKEN` na ně stačí pro veřejné repo;
  pro **private** monorepo `kas-platform-v1` dej fine-grained PAT jako
  repo secret `EDPA_TOKEN`).

**Bez `EDPA_TOKEN` (nebo bez `--with-ci`):**
- Attribution běží dál z lokální evidence — commit authors a
  `/contribute` directives se zapisují post-commit hookem do `evidence[]`
  lokálně. Ztratíš jen PR-review/PR-comment signály (reviewer kredit).
- **Manuální fallback při close** (pokud chceš započítat otevřené PR):
  `python3 .edpa/engine/scripts/sync_pr_contributions.py --pr <N> --rebuild --skip-commit`
  per otevřený PR — viz §3 Stage 2a.

**Setup tokenu (jen pokud chceš `--with-ci`, ~5 min):**
1. **Vytvoř fine-grained PAT** — Resource owner = `kashealth`,
   Repository access = `kas-platform-v1`. Permissions: Repository
   `Contents`+`Pull requests`+`Issues`=read, `Metadata`=read. (Žádné
   org `Projects`/`Members` scopes — V2 GitHub Project neřeší.)
2. **Ulož jako repo secret** `EDPA_TOKEN` v *Settings → Secrets and
   variables → Actions → New repository secret*.
3. **Ověř** mergem PR, který referencuje EDPA item — Actions tab musí
   ukázat ✓ Success na "EDPA Contribution Sync" a do daného
   `.edpa/backlog/<…>.md` se dopíše `evidence[]`.

**Rotace tokenu:** Fine-grained PATs povinně expirují (max 1 rok).
Do týmového kalendáře recurring event "Rotate EDPA_TOKEN" 2 týdny
před expirací.

## 2. Naplnit počáteční backlog

`backlog.py add` je **local-first** — žádné `gh` volání při create.
ID se přidělí z `.edpa/config/id_counters.yaml` (`I-1`, `E-12`, `S-42`),
MCP `edpa_item_create` zvaliduje parent hierarchii (Story→Feature,
Feature→Epic, Epic→Initiative), zapíše se `.edpa/backlog/<typ>/{ID}.md`
a auto-commitne `feat(<ID>): <title>`. PR-derived signály dorazí
asynchronně přes `--with-ci` workflow (ne při create).

```bash
python3 .edpa/engine/scripts/backlog.py add --type Initiative --title "Medical Platform MVP" --js 0
python3 .edpa/engine/scripts/backlog.py add --type Epic --parent I-1 --title "OMOP datový e-shop" --js 21 --status Funnel
python3 .edpa/engine/scripts/backlog.py add --type Story --parent F-1 --title "Implement OMOP parser" \
  --js 5 --iteration PI-2026-1.1 \
  --contributor turyna-martin:owner:0.7 --contributor matousek-daniel:reviewer:0.3

# Validace frontmatteru + ID konzistence:
python3 .edpa/engine/scripts/validate_syntax.py --strict .edpa/backlog/
python3 .edpa/engine/scripts/validate_ids.py
```

(Z Claude Code ekvivalentně `/edpa:add Story "Implement OMOP parser"
--parent F-1 --js 5 --iteration PI-2026-1.1`.)

`--contributor PERSON:ROLE:CW` seedne počáteční `contributors[]` (role
∈ {owner, key, reviewer, consulted}); engine je při close přepočítá
z nasbírané `evidence[]` (viz §3 Stage 2b). Manuální korekce kdykoli
přes `/contribute @person weight:N` v těle commitu / PR / issue.

První PI typicky: 1 Initiative, 2–3 Epics, 4–6 Features, 8–12 Stories
napříč PI-2026-1.{1..4}.

## 3. Weekly cadence

Každé pondělí ráno (= konec předchozí týdenní iterace):

```bash
# Close uplynulou iteraci (prep + engine + reports)
/edpa:close-iteration PI-2026-1.X
```

(Žádný `sync.py pull` — V2 nemá bidirectional sync. Lokální `.edpa/`
JE source of truth.)

`/edpa:close-iteration` má tři formy:

| Forma | Co dělá |
|-------|---------|
| `<iter>` | Full close: prep prompt (capacity overrides) → engine → reports |
| `<iter> --prep-only` | Jen prep: zaznamená override, necommitne engine. Pro mid-iteration recording (PTO oznámí v úterý, close je v pátek). |
| `<iter> --skip-prep` | Engine + reports bez prep promptu. Pro re-run / scripted close. |

**Stage 1 (prep)** se interaktivně zeptá *"Did anyone have non-baseline
capacity?"* a volá `capacity_override.py <iter> --add` per osobu.
Validuje proti people.yaml, computes diff vs baseline, prompts for audit
note, auto-commits s `<iter>: capacity override <person> -> <hours>h
(<note>)`. Closed iterations odmítnou override.

**Stage 2a (volitelně, jen s `--with-ci`)** — mid-flight PR sync: pro
každý **otevřený** PR referencující item v zavírané iteraci spusť
`sync_pr_contributions.py --pr <N> --rebuild --skip-commit`, ať engine
vidí i evidence z PR, které ještě nejsou merged. Přeskoč, když
`EDPA_NO_GH=1` nebo workflow file chybí.

**Stage 2b (POVINNÉ — neskipovat)** — refresh `contributors[]`:

```bash
python3 .edpa/engine/scripts/detect_contributors.py --all-items
```

Engine čte `contributors[]` (normalizovaná per-item CW mapa), NE
`evidence[]` (raw signal log). Post-commit hook a `sync_pr_contributions.py`
píšou jen `evidence[]`. Bez tohoto kroku engine vidí prázdné contributors
a vrátí **0h derived** pro každý item, který přišel přes evidence — bez
erroru, jen tiché nuly. Idempotentní (items bez evidence = no-op),
auto-commit `chore(contributors): …`.

**Stage 2c — engine + reports:**

```bash
# Engine: derived hours z delivery evidence + capacity overrides
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.X
# Reports: per-person timesheety + team rollup
python3 .edpa/engine/scripts/reports.py PI-2026-1.X
```

Engine vyrobí `.edpa/reports/iteration-PI-2026-1.X/edpa_results.json` +
`edpa-results.xlsx` (Team Summary + Item Costs tabs) a zapíše frozen
snapshot `.edpa/snapshots/PI-2026-1.X.json` (s `payload_signature` +
`frozen_at`). Reports vyrobí `timesheet-<id>.md` per osobu +
`timesheet-team.md`. Oboje auto-commitne.

## 4. PI close (po 5 týdnech)

Po zavření všech 5 iterací udělej PI-level rollup:

```bash
python3 .edpa/engine/scripts/pi_close.py --pi PI-2026-1
```

(Agreguje všechny `iteration-PI-2026-1.*/` výsledky do PI summary.
Stage 1 prep se přeskočí — overrides žijí na per-iteration files.)
Per-person timesheety přes PI: `reports.py --pi PI-2026-1` (PI-level rollup).

Audit-grade podpis snapshotu (BankID) je volitelná nadstavba, viz
`docs/audit-trail.md`. Každý iteration snapshot už nese
`payload_signature` (deterministický hash payloadu) + `frozen_at`.

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
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.3 \
  --add --person urbanek-jaroslav --hours 16 --note "vacation Jun 9-11 (3 dny PTO cert)"
```

`--person` musí být `id` z `people.yaml`. Standalone `--list` / `--remove`
viz `--help`. Po změně capacity re-run `engine.py --iteration PI-2026-1.3`,
ať reports reflektují novou alokaci.

### 5.2 MAD validation vs PM ground truth

Single calculation path konverguje přes Story/Defect Done credit + gate
events + yaml_edit signals. Při PI-1 close porovnej engine output
s manuálním PM odhadem:

```bash
# Kanonický výstup vyrobí /edpa:close-iteration (nebo přímo engine.py):
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.1

# PM napíše per-person odhad ručně (gut estimate) do PI close retro a porovná
# se sloupcem "Hours" v edpa-results.xlsx / timesheet-<id>.md.
```

**Acceptance — POZOR, V2 invariant je tvrdá rovnost:** engine validuje
**Σ per-person derived == capacity** (per osobu, tolerance 0.1 h;
`ratio_sum == 1.0`). NENÍ to `derived ≤ cap` jako naznačoval V1 — engine
normalizuje hodiny tak, aby každé osobě seděly přesně na její capacity
(včetně override). To znamená, že i IP iterace s víc strategií než
delivery rozdělí celou capacity — yaml_edit / gate signály zachytí
strategickou práci automaticky, takže se hodiny nikam "neztratí".
MAD ≤ 15 % se měří na **rozdělení mezi osoby/items** vůči PM gut estimate,
ne na celkový součet (ten je z definice == capacity).

Recalibration signal weights (až po nasbírání ≥ 20 ground-truth CW
záznamů z reálného PI): `/edpa:autocalib` (`calibrate_signals.py` —
Monte Carlo nad signal weights + coordinate descent, metrika MAD vs
ground truth). Před tím není kalibrace potřeba — pilot běží na seeded
defaultech z `cw_heuristics.yaml`.

### 5.3 Rollback

- **Stop pilotu** = nech být, nebo smaž `.edpa/` (lokální data) — žádný
  GitHub Project se neprovisioval, takže není co rušit. Git historie
  commitů zůstává jako audit trail (nebo `git revert` EDPA commitů).
- Engine warns `0 evidence pairs` / 0h derived → ověř, že (a)
  `.edpa/backlog/` má seedované Stories s `iteration:` polem a
  status=Done, a (b) **proběhl Stage 2b** (`detect_contributors.py
  --all-items`) — nejčastější příčina tichých nul je vynechaný refresh
  `contributors[]`. yaml_edit signály naběhnou automaticky, pokud jsou
  commits nad `.edpa/backlog/<typ>/<id>.md` v okně iterace.
- `sh preflight.sh` můžeš spustit kdykoli pro re-validation lokálního stavu.

## 6. Success criteria

| # | Kritérium | Měření |
|---|-----------|--------|
| 1 | EDPA produkuje per-person timesheety pro všechny 4 členy s Σ = capacity | reports + manual review |
| 2 | `edpa-results.xlsx` (Team Summary + Item Costs tabs) je akceptovatelný pro audit | manual cross-check vs governance-reseni-v3.md rates |
| 3 | Engine produkuje "rozumné" rozdělení hodin vs PM odhad (MAD ≤ 15 %) | diff (§ 5.2) + PM review |
| 4 | Žádná Layer-1 governance ceremonie nebyla zbytečně přidaná (žádný timesheet, žádný TS-tracking tool) | retro feedback od týmu |
| 5 | Setup → first iteration close ≤ 30 min člověka času | log time-to-close |
| 6 | Auto-commit / local-first attribution drží state přes 5+ PR mergů | `git log` ukáže `feat(<ID>):` + `chore(contributors):` commits in-place |

Pokud 5+ z 6 PASS → pilot úspěšný, pokračuj na PI-2026-2 (full prod) a zveřejni jako case study.

## 7. Open questions (pre-kickoff sync)

1. **PI cadence** — 1-week × 5 (default) vs 2-week × 5? Nastavitelné v `cadence:` (edpa.yaml + people.yaml, musí se shodovat).
2. **FTE distribuce** — 1.0 / 0.5 / 0.25 per člen? Doporučení v `people.yaml.example`.
3. **Cost reporting** — sazby drží **privátní registr** (ne EDPA people.yaml — engine `hourly_rate` nečte). Auditor format = open question.
4. **Calibration timing** — `/edpa:autocalib` až po PI-2026-1 close (potřeba ≥ 20 ground truth records).
5. **PTO / sick policy** — kdo zapisuje override? Návrh: každý člen sám commituje vlastní entry před close; PM/Lead audit-checkne weekly.
6. **IP iterace overtime** — standard "+4h IP push", nebo ad-hoc? Pokud standard → preventivně override v PI-2026-1.5.
7. **PR-signal sync** — zapnout `--with-ci` + `EDPA_TOKEN` pro reviewer kredit, nebo stačí lokální commit-author evidence? (Private repo → fine-grained PAT, viz §1.1.)

## 8. Reference

- Methodology: [`docs/methodology.md`](../methodology.md) (EDPA 2.1.8 spec)
- V2 architecture decisions: [`docs/v2/decisions.md`](../v2/decisions.md) — ADR-012 (local-first add), ADR-013 (PR-signal CI materialization)
- Dev ID collisions (local-first allocator): [`docs/dev-collisions.md`](../dev-collisions.md)
- `/contribute` directive: [`docs/contribute-directive.md`](../contribute-directive.md)
- E2E V2 validation: [`docs/e2e-v2-full.md`](../e2e-v2-full.md) — full install → add → close → report run
- CHANGELOG: [`CHANGELOG.md`](../../CHANGELOG.md)
- Governance design: [`docs/examples/governance-kashealth/governance-reseni-v3.md`](../examples/governance-kashealth/governance-reseni-v3.md)
