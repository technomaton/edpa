# EDPA Playbook -- Od nuly po prvni PI

Kompletni prirucka pro nasazeni metodiky EDPA (Evidence-Driven Proportional Allocation) na novy projekt. Od prazdneho repozitare po uzavreni prvniho Planning Intervalu a kalibraci heuristik.

**Verze:** EDPA v1.0.0-beta
**Posledni aktualizace:** 2026-03-28

---

## Obsah

1. [Prerekvizity](#prerekvizity)
2. [Faze 1: Infrastruktura (Den 1)](#faze-1-infrastruktura-den-1--4-hodiny)
3. [Faze 2: Prvni iterace (Tyden 1-2)](#faze-2-prvni-iterace-tyden-1-2)
4. [Faze 3: PI Close (Po 4-5 iteracich)](#faze-3-pi-close-po-4-5-iteracich)
5. [Faze 4: Kontinualni provoz](#faze-4-kontinualni-provoz)
6. [Checklist -- Co mit hotove](#checklist--co-mit-hotove)
7. [CLI Reference](#cli-reference)
8. [Architektura](#architektura)
9. [Troubleshooting](#troubleshooting)

---

## Prerekvizity

### Nastroje

| Nastroj | Minimalni verze | Overeni |
|---------|-----------------|---------|
| Python | 3.10+ | `python --version` |
| PyYAML | libovolna | `pip install pyyaml` |
| GitHub CLI (gh) | 2.40+ | `gh --version` |
| Git | 2.30+ | `git --version` |

### GitHub CLI scopes

```bash
gh auth login
gh auth refresh -s repo,project,read:project,admin:org
```

Overeni:

```bash
gh auth status
# Musi ukazovat scopes: repo, project, admin:org
```

### Organizace a tym

Pred zacatkem je treba mit:

- GitHub organizaci (napr. `my-org`)
- Definovany tym: jmena, role (Arch, Dev, DevSecOps, PM, QA, BO), FTE, kapacity
- Alespon zakladni backlog (1 Epic, 2-3 Features, 5-10 Stories)

### Role v EDPA

| Role | Popis | Typicke evidence v Gitu |
|------|-------|------------------------|
| BO | Business Owner | Issue komentare, validace |
| PM | Product Manager / Product Owner | Backlog management, specifikace |
| Arch | Architekt | Code review, design decisions |
| Dev | Vyvojar | Commity, PR, assignee |
| DevSecOps | DevSecOps Engineer | CI/CD, security, infra commity |
| QA | Test Engineer | Testovaci commity, review |

---

## Faze 1: Infrastruktura (Den 1, ~4 hodiny)

### Cesta A: Claude Code (doporuceno)

V terminalu s Claude Code nainstalovanym:

```
/edpa setup
```

Claude Code provede kroky 1.1-1.6 automaticky -- vytvori repo, nakonfiguruje tym, nastavi Issue Types a vytvori GitHub Project.

### Cesta B: Manualni CLI

Nasledujici kroky popisuji manualni postup bez Claude Code.

### 1.1 Nainstalovat EDPA plugin

**Varianta A: Shell installer (doporuceno)**

```bash
cd my-project
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

**Varianta B: Manualni kopie**

```bash
cd my-project
gh repo clone technomaton/edpa /tmp/edpa
cp -r /tmp/edpa/plugin/ .claude/
rm -rf /tmp/edpa
```

Vysledna struktura:

```
my-project/
  .edpa/
    config/
      edpa.yaml          # Hlavni konfigurace
      people.yaml        # tym a projekt
      people.yaml      # Kapacitni registr
      heuristics.yaml    # CW heuristiky
      project.yaml       # Projektova konfigurace
    backlog/
      initiatives/       # 1 soubor = 1 initiative
      epics/             # 1 soubor = 1 epic
      features/          # 1 soubor = 1 feature
      stories/           # 1 soubor = 1 story
    data/
      ground_truth.yaml  # Ground truth (po PI)
      calibration_log.tsv
    reports/             # Generovane reporty per iterace
    snapshots/           # Zmrazene snapshoty iteraci
    changelog.jsonl      # Changelog syncu
    sync_state.json      # Stav posledni synchronizace
    iterations/          # Plany a vysledky iteraci
  .claude/edpa/
    scripts/
      engine.py          # EDPA vypocetni jadro
      backlog.py         # Sprava backlogu (tree, show, wsjf, validate)
      sync.py            # Bidirekcni sync GitHub Projects <-> Git
      issue_types.py     # Sprava Issue Types na org urovni
      project_setup.py   # Automaticke vytvoreni GitHub Projectu
      project_views.py   # Views setup (template, instrukce, verifikace)
      create_project_views.py  # Playwright automatizace views (volitelne)
      evaluate_cw.py     # CW kalibrace (MAD evaluator)
    templates/
      people.yaml.tmpl      # Sablona kapacitniho registru
      heuristics.yaml.tmpl    # Sablona CW heuristik
      project.yaml.tmpl       # Sablona projektove konfigurace
  .github/workflows/
    branch-check.yml     # CI: kontrola branch naming
    iteration-close.yml  # CI: uzavreni iterace (workflow_dispatch)
    sync-projects-to-git.yml   # Cron: Projects -> Git (15 min)
    sync-git-to-projects.yml   # Push trigger: Git -> Projects
  docs/                  # Dokumentace
```

### 1.2 Nakonfigurovat tym (people.yaml)

```bash
cp .claude/edpa/templates/people.yaml.tmpl .edpa/config/people.yaml
```

Upravit `.edpa/config/people.yaml`:

```yaml
cadence:
  # AI-native default: 5-tydenni PI = 4 dodavkove iterace po 1 tydnu + 1 IP
  # tyden na dluh, prioritizaci a PI planning (s AI zvladnutelne za den).
  # Classic SAFe (2-tydenni iterace, 10-tydenni PI) zustava podporovany —
  # nastav iteration_weeks: 2 + pi_weeks: 10.
  iteration_weeks: 1                    # 1 (AI-native, default) nebo 2 (classic)
  pi_weeks: 5                           # 5 (AI-native, default) nebo 10 (classic)
  delivery_iterations_per_pi: 4         # PI minus IP iterace
  ip_iterations_per_pi: 1              # Innovation & Planning

teams:
  - id: "Muj Tym"
    planning_factor: 0.8               # Planujeme na 80% kapacity

people:
  - id: alice
    name: "Alice Novakova"
    role: Arch                          # Arch, Dev, DevSecOps, PM, QA, BO
    team: "Muj Tym"
    fte: 0.5
    capacity_per_iteration: 20          # hodiny: FTE x 40 pro 1-tydenni iter.
                                        # (40 pro 2-tydenni)
    email: "alice@example.com"
    availability: confirmed             # confirmed, partial, unavailable

  - id: bob
    name: "Bob Svoboda"
    role: Dev
    team: "Muj Tym"
    fte: 1.0
    capacity_per_iteration: 40          # FTE x 40 pro 1-tydenni iter.
    email: "bob@example.com"
    availability: confirmed

  # Pridat dalsi cleny tymu...
```

**Dulezite:** `planning_factor` je planovaci heuristika (planujeme na 80%). EDPA engine pocita vzdy se 100% kapacity -- buffer absorbuje neplanovane prace.

Tym a projekt se zaroven konfiguruje v `.edpa/config/people.yaml`:

```yaml
# .edpa/config/people.yaml
project:
  name: "Nazev projektu"
  organization: "Vase org"

people:
  - id: dev1
    name: "Developer"
    email: "dev@example.com"
    role: Dev
    team: "Core"
    fte: 1.0
    capacity: 80
```

### 1.3 Nakonfigurovat projekt (project.yaml)

```bash
cp .claude/edpa/templates/project.yaml.tmpl .edpa/config/project.yaml
```

Upravit `.edpa/config/project.yaml`:

```yaml
project:
  name: "Muj Projekt"
  registration: ""                      # Cislo registrace (pokud existuje)
  program: ""                           # Program financovani
  organizations:
    - name: "Moje Organizace"
  domain: "mujprojekt.cz"

governance:
  methodology: "EDPA v1.0.0-beta"
  calculation_mode: "simple"            # simple (JS x CW) nebo full (JS x CW x RS)
  audit_mode: "full"

naming:
  pi_pattern: "PI-{year}-{pi_num}"                    # PI-2026-1
  iteration_pattern: "PI-{year}-{pi_num}.{iter_num}"  # PI-2026-1.3
  branch_pattern: "{type}/{item_id}-{description}"    # feature/S-200-omop-parser
  item_prefixes:
    initiative: "I"
    epic: "E"
    feature: "F"
    story: "S"
    task: "T"
    bug: "B"
```

### 1.4 Nakonfigurovat CW heuristiky

```bash
cp .claude/edpa/templates/heuristics.yaml.tmpl .edpa/config/heuristics.yaml
```

Vychozi hodnoty jsou kalibrovane Monte Carlo simulaci (1000 scenaru, 66 362 zaznamu, p<0.001). Pro zacatek staci bez uprav. Kalibrace na vlastni data se provadi po prvnim PI (viz [Faze 3](#33-kalibrace-cw-heuristik)).

Klicove vychozi hodnoty:

| Evidence role | CW vaha |
|---------------|---------|
| owner (assignee) | 1.00 |
| key (PR author) | 0.60 |
| reviewer (commit/PR review) | 0.25 |
| consulted (komentar) | 0.15 |

Role-specificke korekce (strategicke role jsou Gitem podhodnoceny):

| Role | Korekce | Duvod |
|------|---------|-------|
| BO consulted | 0.30 (+0.15) | Rozhodovani neviditelne v Gitu |
| PM consulted | 0.20 (+0.05) | Specifikace neviditelna v Gitu |
| Arch reviewer | 0.30 (+0.05) | Design review neviditelny |

### 1.5 Nakonfigurovat .edpa/config/edpa.yaml a iterations/

`edpa.yaml` od v1.5.0 obsahuje pouze stabilní governance / sync konfiguraci.
PI a iterace žijí v `.edpa/iterations/` jako samostatné soubory:

```yaml
# .edpa/iterations/PI-2026-1.yaml — PI-level metadata
pi:
  id: PI-2026-1
  status: active
  iteration_weeks: 1                      # AI-native default
  pi_iterations: 5                         # 4 delivery + 1 IP
  start_date: 2026-04-01
  end_date: 2026-05-05
```

```yaml
# .edpa/iterations/PI-2026-1.1.yaml — per-iteration data
iteration:
  id: PI-2026-1.1
  pi: PI-2026-1
  start_date: 2026-04-01
  end_date: 2026-04-07
  weeks: 1
  status: planned
# planning / delivery / stories_detail follow as the iteration runs
```

Vytvoř obdobně `PI-2026-1.{2..5}.yaml`. Poslední iterace dostane
`type: IP` (Innovation & Planning). Kontinuitu (žádné mezery /
překryvy, `weeks` × 7 ≈ rozdíl dat) hlídá `validate_iterations.py`
i automatický PostToolUse hook.

```yaml
# Sync nastaveni
sync:
  github_org: "my-org"                  # <-- Vase organizace
  github_project_number: 1              # <-- Cislo projektu (az po vytvoreni)
  sync_interval: "15m"
  auto_commit: true
```

### 1.6 Nastavit Issue Types na organizaci

Issue Types jsou nativni GitHub feature na urovni organizace (ne labels, ne custom fields).

```bash
# Zobrazit aktualni typy
python .claude/edpa/scripts/issue_types.py list --org my-org

# Vytvorit EDPA sadu Issue Types
python .claude/edpa/scripts/issue_types.py setup --org my-org

# Dry-run (jen ukaze co by se stalo)
python .claude/edpa/scripts/issue_types.py setup --org my-org --dry-run
```

EDPA vytvori tyto Issue Types:

| Typ | Barva | Popis |
|-----|-------|-------|
| Initiative | PINK | Business case, investicni zamer |
| Epic | PURPLE | Strategicky cil, 6-9 mesicu |
| Feature | BLUE | Musi se vejit do Planning Intervalu |
| Story | GREEN | Dodavano v iteraci |
| Defect | RED | Defekt v existujici funkcionalite |
| Task | YELLOW | Technicka prace |

> **Poznamka:** Enabler je **label** (Business vs Enabler klasifikace, SAFe), ne Issue Type. Epic muze mit label "Enabler" pro oznaceni Enabler Epicu.

### 1.7 Naplnit backlog

EDPA pouziva file-per-item strukturu -- kazdy work item je samostatny YAML soubor:

```
.edpa/
  config/
    edpa.yaml                    # hlavni konfigurace
    people.yaml                  # tym a projekt
    people.yaml                # kapacitni registr
    heuristics.yaml              # CW heuristiky
    project.yaml                 # projektova konfigurace
  backlog/
    initiatives/
      I-1.yaml                   # 1 soubor = 1 initiative
    epics/
      E-1.yaml                   # 1 soubor = 1 epic
    features/
      F-1.yaml                   # 1 soubor = 1 feature
    stories/
      S-1.yaml                   # 1 soubor = 1 story
  iterations/
    PI-2026-1.1.yaml             # plan iterace
```

Priklad story souboru (`.edpa/backlog/stories/S-1.yaml`):
```yaml
id: S-1
type: Story
title: "Implementace parseru"
status: Backlog
parent: F-1
js: 5
assignee: dev1
iteration: PI-2026-1.1
```

Pridani noveho itemu:
```bash
# Claude Code:
/edpa setup    # interaktivne prida items

# CLI:
python .claude/edpa/scripts/backlog.py add --type Story --parent F-1 --title "..." --js 5 --assignee dev1
python .claude/edpa/scripts/backlog.py add --type Epic --title "..." --js 13 --bv 13 --tc 8 --rr 5
```

Overit integritu:

```bash
python .claude/edpa/scripts/backlog.py validate
```

Zobrazit hierarchii:

```bash
python .claude/edpa/scripts/backlog.py tree
python .claude/edpa/scripts/backlog.py tree --level epic
```

Zobrazit WSJF prioritizaci:

```bash
python .claude/edpa/scripts/backlog.py wsjf
python .claude/edpa/scripts/backlog.py wsjf --level feature
```

Zobrazit detail polozky:

```bash
python .claude/edpa/scripts/backlog.py show S-200
python .claude/edpa/scripts/backlog.py show E-10
```

### 1.8 Vytvorit GitHub Project

```bash
python .claude/edpa/scripts/project_setup.py \
  --org my-org \
  --repo my-project \
  --project-title "EDPA -- Muj Projekt"
```

Dry-run:

```bash
python .claude/edpa/scripts/project_setup.py \
  --org my-org \
  --repo my-project \
  --dry-run
```

Skript provede 7 kroku:

1. Overi Issue Types na org (musi byt spusten `issue_types.py setup` predtim)
2. Vytvori GitHub Project v2 na org urovni
3. Vytvori custom fields: Job Size, Business Value, Time Criticality, Risk Reduction, WSJF Score (NUMBER), Team (SINGLE_SELECT)
4. Linkuje projekt k repozitari
5. Vytvori issues z item files v `.edpa/` s nativnimi Issue Types
6. Nastavi field values (JS, BV, TC, RR, WSJF, status) na vsech project items
7. Aktualizuje `.edpa/config/edpa.yaml` s cislem projektu pro sync

### 1.9 Nastavit Project views

GitHub Projects v2 API nepodporuje vytvareni views programaticky. Jsou dve cesty:

**Cesta A: Manual setup s instrukce generatorem**

```bash
python .claude/edpa/scripts/project_views.py instructions --org my-org --project 1
```

Skript vygeneruje presne kliknuti pro vytvoreni 6 views:

| View | Typ | Filtr/Razeni |
|------|-----|-------------|
| All Items | Table | Vsechny polozky |
| Board | Board | Funnel / Analyzing / Backlog / Implementing / Done |
| Epics | Table | `type:Epic`, razeno WSJF |
| Features | Table | `type:Feature`, razeno WSJF |
| Stories | Table | `type:Story`, filtrovano iteraci |
| WSJF Ranking | Table | Razeno WSJF sestupne |

**Cesta B: Oznacit jako sablonu (pro dalsi projekty)**

```bash
python .claude/edpa/scripts/project_views.py template --org my-org --project 1
```

**Cesta C: Vytvorit novy projekt ze sablony**

```bash
python .claude/edpa/scripts/project_views.py create-from-template \
  --org my-org \
  --template 1 \
  --title "Novy Projekt"
```

**Overeni:**

```bash
python .claude/edpa/scripts/project_views.py verify --org my-org --project 1
```

**Cesta D: Playwright automatizace (volitelne)**

Pokud chcete plne automaticke vytvoreni views:

```bash
pip install playwright && playwright install chromium
python .claude/edpa/scripts/create_project_views.py
```

Prvni spusteni: otevre prohlizec -> prihlasit se -> views se vytvori automaticky.

### 1.10 Overit setup

```bash
# Demo EDPA engine (bez realnych dat)
python .claude/edpa/scripts/engine.py --demo

# Validace backlogu
python .claude/edpa/scripts/backlog.py validate

# Status projektu
python .claude/edpa/scripts/backlog.py status

# Sync status
python .claude/edpa/scripts/sync.py status
```

### 1.11 Commitnout zakladni konfiguraci

```bash
git add .edpa/config/people.yaml .edpa/config/project.yaml .edpa/config/heuristics.yaml
git add .edpa/
git commit -m "feat(edpa): initial EDPA setup for my-project"
git push origin main
```

---

## Faze 2: Prvni iterace (Tyden 1-2)

### 2.1 Iteration Planning

1. **Potvrzeni kapacity** -- tym potrdi dostupnost na iteraci
2. **Vyber stories** -- z backlogu dle WSJF poradi, na 80% kapacity

```bash
# WSJF ranking features
python .claude/edpa/scripts/backlog.py wsjf --level feature

# Tree pro konkretni iteraci
python .claude/edpa/scripts/backlog.py tree --iteration PI-2026-1.1
```

3. **Prirazeni assignees** -- kazda story musi mit assignee
4. **Aktualizace backlogu** -- `iteration: PI-2026-1.1` na vybranych stories

### 2.2 Denni prace

**Branch naming konvence** (CI kontrola v `.github/workflows/branch-check.yml`):

```bash
# Format: {type}/{ITEM_ID}-{popis}
git checkout -b feature/S-200-omop-parser
git checkout -b feature/F-102-anon-engine
git checkout -b bugfix/S-215-upload-validation
git checkout -b chore/T-050-ci-pipeline
```

Povolene typy: `feature`, `bugfix`, `hotfix`, `chore`
Povolene prefixy: `S` (Story), `F` (Feature), `E` (Epic), `T` (Task), `B` (Bug), `I` (Initiative), `A` (architektura)

**Commit konvence:**

```bash
git commit -m "feat(S-200): implement OMOP CDM parser"
git commit -m "fix(S-215): validate upload file size"
git commit -m "test(S-201): add unit tests for parser"
git commit -m "docs(E-10): update epic hypothesis"
```

EDPA engine rozpoznava reference `S-XXX`, `F-XXX`, `E-XXX` v commitech a PR pro detekci evidence.

**Pull Request workflow:**

```bash
git push origin feature/S-200-omop-parser
gh pr create --title "S-200: OMOP CDM parser implementation" \
  --body "Closes #42

## Changes
- Implemented OMOP CDM parser
- Added schema validation

## Testing
- Unit tests: 15 passing
"
```

PR review = evidence pro EDPA (reviewer dostane CW dle role).

### 2.3 Sync (automaticky)

Bidirekcni synchronizace mezi GitHub Projects (UI pro PM/BO) a item files v `.edpa/` (Git-native):

**Automaticky pres GitHub Actions:**

- `sync-projects-to-git.yml` -- kazych 15 minut stahuje zmeny z Projects do Gitu
- `sync-git-to-projects.yml` -- pri push do `main` s zmenou v `.edpa/` propaguje do Projects

**Manualne:**

```bash
# Pull: GitHub Projects -> item files in .edpa/
python .claude/edpa/scripts/sync.py pull

# Push: item files in .edpa/ -> GitHub Projects
python .claude/edpa/scripts/sync.py push

# Diff: zobrazit co by se zmenilo
python .claude/edpa/scripts/sync.py diff

# Changelog
python .claude/edpa/scripts/sync.py log

# Status
python .claude/edpa/scripts/sync.py status

# Konflikty
python .claude/edpa/scripts/sync.py conflicts
```

**Testovani syncu (bez GitHub API):**

```bash
python .claude/edpa/scripts/sync.py pull --mock
python .claude/edpa/scripts/sync.py diff --mock
```

### 2.4 Iteration Close

Na konci kazde iterace (po 2 tydnech):

**Claude Code (doporuceno):**

```
/edpa close-iteration PI-2026-1.1
```

Claude Code stahne evidenci, spusti EDPA engine a vygeneruje reporty automaticky.

**Manualni CLI:**

```bash
python .claude/edpa/scripts/engine.py \
  --iteration PI-2026-1.1 \
  --capacity .edpa/config/people.yaml \
  --heuristics .edpa/config/heuristics.yaml
```

Nebo pres GitHub Actions (workflow_dispatch):

1. Jit na Actions -> EDPA Iteration Close
2. Zadat iteration_id: `PI-2026-1.1`
3. Zvolit mode: `simple` nebo `full`
4. Spustit

**Vystupy:**

```
.edpa/reports/iteration-PI-2026-1.1/
  edpa_results.json      # Kompletni vypocet (JSON)
  vykaz-alice.md         # Vykaz pro kazdou osobu
  edpa-results.xlsx      # Team Summary + Item Costs tabs (Excel)
.edpa/snapshots/
  PI-2026-1.1.json       # Zmrazeny snapshot
```

**Rezim vypoctu:**

| Rezim | Vzorec | Pouziti |
|-------|--------|---------|
| simple | JS x CW | Vychozi -- Job Size x Contribution Weight |
| full | JS x CW x RS | S Role Strength -- pro presnejsi alokaci |

**Invarianty** (engine automaticky kontroluje):

- Soucet hodin osoby = jeji kapacita (odchylka < 0.01h)
- Soucet pomeru = 1.0 (odchylka < 0.001)
- Zadne zaporne hodiny
- Pokud invariant selze, engine hlasi `FAIL`

### 2.5 Aktualizace iteracniho planu

Po uzavreni iterace vytvorit/aktualizovat iteracni soubor:

```
.edpa/iterations/PI-2026-1.1.yaml
```

Priklad struktury:

```yaml
iteration:
  id: PI-2026-1.1
  pi: PI-2026-1
  start_date: 2026-04-01
  end_date: 2026-04-14
  weeks: 2
  status: closed

planning:
  capacity: 380
  planning_factor: 0.80
  planned_sp: 24
  stories:
    - S-200
    - S-201
    - S-202

delivery:
  delivered_sp: 24
  predictability: "100%"
  velocity: 24
  spillover: []
  unplanned: []
  notes: "Prvni iterace -- plny delivery."
```

---

## Faze 3: PI Close (Po 4-5 iteracich)

### Cesta A: Claude Code (doporuceno)

```
/edpa calibrate
```

Claude Code spusti CW kalibraci, vyhodnoti MAD a navrh uprav heuristik. Pro generovani reportu:

```
/edpa reports
```

### Cesta B: Manualni CLI

Nasledujici kroky popisuji manualni postup.

### 3.1 Retrospektiva

Na konci PI (po 4 delivery iteracich + 1 IP iterace):

1. **Projit auto-detekci vs. realita** na 5-10 stories
2. Pro kazdou story porovnat:
   - Kdo byl auto-detekovan jako contributor?
   - Jake CW engine priradil?
   - Co tim ohodnotil?
   - Odpovida realite?

### 3.2 Zaznamenat ground truth

Vytvorit `.edpa/data/ground_truth.yaml`:

```yaml
# Ground truth pro CW kalibraci
# Zaznamenano na PI retrospektive
# Kazdy zaznam: co engine urcil vs. co tym potvrdil

records:
  - item_id: S-200
    person_id: alice
    evidence_role: reviewer          # Co engine detekoval
    auto_cw: 0.25                    # CW z heuristik
    confirmed_cw: 0.35               # Co tym potvrdil
    person_role: Arch                # Role z people.yaml
    notes: "Alice delala design review + architektonicke rozhodnuti"

  - item_id: S-200
    person_id: bob
    evidence_role: owner
    auto_cw: 1.00
    confirmed_cw: 1.00
    person_role: Dev
    notes: "Presne -- Bob byl assignee a udelal vsechnu praci"

  - item_id: S-201
    person_id: carol
    evidence_role: consulted
    auto_cw: 0.15
    confirmed_cw: 0.20
    person_role: PM
    notes: "Carol definovala AC a testovala -- vice nez jen komentar"

  # ... alespon 20 zaznamu pro kalibraci
```

**Doporuceni:** Zaznamenat alespon 20 zaznamu (minimum pro `evaluate_cw.py`). Idealne 30-50 pro statistickou relevanci.

### 3.3 Kalibrace CW heuristik

```bash
python .claude/edpa/scripts/evaluate_cw.py \
  --ground-truth .edpa/data/ground_truth.yaml \
  --heuristics .edpa/config/heuristics.yaml
```

Vystup:

```
MAD=0.041200
RECORDS=20
TOTAL_DEVIATION=0.824000
```

**Interpretace MAD (Mean Absolute Deviation):**

| MAD | Hodnoceni | Akce |
|-----|-----------|------|
| < 0.03 | Vyborne | Bez zmeny |
| 0.03 - 0.06 | Dobre | Drobne korekce (volitelne) |
| 0.06 - 0.10 | Prijatelne | Zvazit upravu role_overrides |
| > 0.10 | Spatne | Nutna kalibrace |

**Korekce heuristik:**

Pokud MAD > 0.06, analyzovat kde jsou nejvetsi odchylky:

1. Podivat se na zaznamy kde `abs(auto_cw - confirmed_cw)` je nejvyssi
2. Identifikovat vzory dle role (typicky BO, PM, Arch)
3. Upravit `role_overrides` v `.edpa/config/heuristics.yaml`
4. Znovu spustit evaluaci

### 3.4 Planovani dalsiho PI

1. **Nove epicy/features** -- pridat jako soubory do `.edpa/backlog/epics/` a `.edpa/backlog/features/`
2. **WSJF prioritizace:**

```bash
python .claude/edpa/scripts/backlog.py wsjf
```

3. **Kapacitni planovani** -- aktualizovat `.edpa/config/people.yaml` (zmeny FTE, dostupnost)
4. **Vytvorit nove iteration soubory** v `.edpa/iterations/`:

```yaml
# .edpa/iterations/PI-2026-2.yaml
pi:
  id: PI-2026-2
  status: planning
  iteration_weeks: 2
  pi_iterations: 5
  start_date: 2026-06-10
  end_date: 2026-08-18
```

```yaml
# .edpa/iterations/PI-2026-2.1.yaml
iteration:
  id: PI-2026-2.1
  pi: PI-2026-2
  start_date: 2026-06-10
  end_date: 2026-06-23
  weeks: 2
  status: planned
# ...
```

---

## Faze 4: Kontinualni provoz

### S Claude Code (doporuceno)

Kazda iterace:

```
/edpa close-iteration PI-2026-1.X    # uzavreni iterace
/edpa reports                         # generovani reportu
```

Kazdy PI:

```
/edpa calibrate                       # CW kalibrace
```

### Manualni postup

### Kazda iterace (kazde 2 tydny)

1. **Planning** -- vybrat stories, prirazit assignees
2. **Denni prace** -- branch naming, commity s referencemi, PR review
3. **Iteration Close** -- EDPA engine, generovani reportu
4. **Sync** -- automaticky verzuje zmeny (GitHub Actions cron 15min)
5. **Review** -- tym zkontroluje vykazy, zahlasi korektury

### Kazdy PI (kazych 10 tydnu)

1. **Retrospektiva** -- auto-detected CW vs realita
2. **Ground truth** -- zaznamenat alespon 20 novych zaznamu
3. **CW kalibrace** -- `evaluate_cw.py`, vyhodnotit MAD
4. **Velocity trend** -- porovnat delivery across iteraci
5. **Predictability** -- (delivered_sp / planned_sp) across iteraci

```bash
# Status za celou iteraci
python .claude/edpa/scripts/backlog.py status --iteration PI-2026-1.3

# Celkovy status projektu
python .claude/edpa/scripts/backlog.py status
```

### Automatizace pres GitHub Actions

| Workflow | Trigger | Co dela |
|----------|---------|--------|
| `branch-check.yml` | PR opened/sync | Kontroluje branch naming konvenci |
| `iteration-close.yml` | workflow_dispatch | Spusti EDPA engine, commity vysledky |
| `sync-projects-to-git.yml` | cron (15min) + manual | Pull: Projects -> item files in .edpa/ |
| `sync-git-to-projects.yml` | push na .edpa/ | Push: item files in .edpa/ -> Projects |

---

## Checklist -- Co mit hotove

### Den 1

- [ ] Repo vytvorene s EDPA strukturou
- [ ] `.edpa/config/people.yaml` -- tym s rolemi, FTE, kapacitami
- [ ] `.edpa/config/project.yaml` -- nazev projektu, metadata
- [ ] `.edpa/config/heuristics.yaml` -- vychozi heuristiky (skopirovano ze sablony)
- [ ] `.edpa/config/edpa.yaml` -- PI, iterace, datumy, sync konfigurace
- [ ] Issue Types nastavene na organizaci (`issue_types.py setup`)
- [ ] Backlog naplneny (alespon 1 Epic, 3 Features, 10 Stories)
- [ ] `backlog.py validate` projde bez chyb
- [ ] GitHub Project vytvoren (`project_setup.py`)
- [ ] Project views nastaveny (manualne nebo ze sablony)
- [ ] `engine.py --demo` projde uspesne

### Tyden 1

- [ ] Tym pracuje s branch naming konvenci (`feature/S-XXX-popis`)
- [ ] Commity referuji work items (`feat(S-XXX): ...`)
- [ ] PR reviews probihaji
- [ ] Sync funguje (overit `sync.py status`)
- [ ] Item files v .edpa/ se automaticky aktualizuji z Projects

### Konec iterace 1

- [ ] EDPA engine spusten pro iteraci
- [ ] `edpa_results.json` vygenerovan v `.edpa/reports/`
- [ ] Vykazy vygenerovany (per-person)
- [ ] Vsechny invarianty prosly (`all_invariants_passed: true`)
- [ ] Tym zkontroloval vysledky
- [ ] Iteracni soubor vytvoren v `.edpa/iterations/`

### Konec iterace 2-4

- [ ] Velocity stabilni (odchylka < 20%)
- [ ] Prediktabilita > 80% (delivered / planned)
- [ ] Zadne nevyresene sync konflikty

### Konec PI 1

- [ ] Ground truth zaznamenano (min. 20 zaznamu)
- [ ] CW kalibrace provedena (`evaluate_cw.py`)
- [ ] MAD vyhodnoceno (cil: < 0.06)
- [ ] Heuristiky upraveny (pokud MAD > 0.06)
- [ ] Planovani PI 2 -- nove epicy, WSJF, kapacity
- [ ] `.edpa/config/edpa.yaml` aktualizovan na novy PI

---

## CLI Reference

### Claude Code prikazy (doporuceno)

| Prikaz | Popis |
|--------|-------|
| `/edpa setup` | Pocatecni setup projektu -- repo, tym, Issue Types, GitHub Project |
| `/edpa close-iteration PI-2026-1.X` | Uzavreni iterace -- stazeni evidence, EDPA engine, reporty |
| `/edpa reports` | Generovani reportu a vykazu |
| `/edpa calibrate` | CW kalibrace -- vyhodnoceni MAD, navrh uprav heuristik |

### engine.py -- EDPA vypocetni jadro

| Prikaz | Popis |
|--------|-------|
| `engine.py --demo` | Demo s ukázkovymi daty (3 osoby, 5 polozek) |
| `engine.py --iteration PI-2026-1.3 --capacity .edpa/config/people.yaml --heuristics .edpa/config/heuristics.yaml` | Plny EDPA vypocet pro iteraci |
| `engine.py --iteration ID --mode full ...` | Vypocet s Role Strength (JS x CW x RS) |
| `engine.py --output cesta/vysledek.json ...` | Vlastni vystupni cesta |

### backlog.py -- Sprava backlogu

| Prikaz | Popis |
|--------|-------|
| `backlog.py tree` | Zobrazí plnou hierarchii (I -> E -> F -> S) |
| `backlog.py tree --level epic` | Jen epicy |
| `backlog.py tree --level feature` | Jen features |
| `backlog.py tree --level story` | Jen stories |
| `backlog.py tree --iteration PI-2026-1.1` | Filtr stories na iteraci |
| `backlog.py show S-200` | Detail polozky |
| `backlog.py show E-10` | Detail epicu s features |
| `backlog.py status` | Celkovy status projektu |
| `backlog.py status --iteration PI-2026-1.1` | Status pro iteraci |
| `backlog.py wsjf` | WSJF prioritizace (vsechny urovne) |
| `backlog.py wsjf --level feature` | WSJF jen features |
| `backlog.py validate` | Kontrola integrity backlogu |

### sync.py -- Bidirekcni sync

| Prikaz | Popis |
|--------|-------|
| `sync.py pull` | GitHub Projects -> item files in `.edpa/` |
| `sync.py pull --commit` | Pull + auto-commit (pouziva CI) |
| `sync.py pull --mock` | Simulace bez GitHub API |
| `sync.py push` | item files in `.edpa/` -> GitHub Projects |
| `sync.py push --mock` | Simulace push |
| `sync.py diff` | Zobrazí rozdily (dry-run) |
| `sync.py diff --mock` | Rozdily v mock modu |
| `sync.py log` | Changelog syncu |
| `sync.py log --limit 50` | Poslednich 50 zaznamu |
| `sync.py status` | Stav posledni synchronizace |
| `sync.py conflicts` | Nevyresene konflikty |

### issue_types.py -- Issue Types (org-level)

| Prikaz | Popis |
|--------|-------|
| `issue_types.py list --org ORG` | Zobrazí aktualni typy na org |
| `issue_types.py setup --org ORG` | Vytvori EDPA sadu Issue Types |
| `issue_types.py setup --org ORG --dry-run` | Dry-run setup |
| `issue_types.py assign --org ORG --repo REPO --issue 1 --type Epic` | Priradi typ issue |
| `issue_types.py migrate --org ORG --repo REPO` | Migruje labels -> Issue Types |
| `issue_types.py migrate --org ORG --repo REPO --dry-run` | Dry-run migrace |
| `issue_types.py migrate --org ORG --repo REPO --remove-labels` | Migrace + smazani starych labels |

### project_setup.py -- Inicializace GitHub Projectu

| Prikaz | Popis |
|--------|-------|
| `project_setup.py --org ORG --repo REPO` | Vytvori kompletni Project |
| `project_setup.py --org ORG --repo REPO --project-title "Nazev"` | S vlastnim nazvem |
| `project_setup.py --org ORG --repo REPO --dry-run` | Jen ukaze co by udelal |

### project_views.py -- Project Views

| Prikaz | Popis |
|--------|-------|
| `project_views.py instructions --org ORG --project N` | Instrukce pro manual setup |
| `project_views.py template --org ORG --project N` | Oznaci project jako sablonu |
| `project_views.py create-from-template --org ORG --template N --title "..."` | Novy project ze sablony |
| `project_views.py verify --org ORG --project N` | Overi ze views jsou spravne |

### evaluate_cw.py -- CW Kalibrace

| Prikaz | Popis |
|--------|-------|
| `evaluate_cw.py --ground-truth .edpa/data/ground_truth.yaml --heuristics .edpa/config/heuristics.yaml` | Spocita MAD (Mean Absolute Deviation) |

### Dalsi skripty

| Prikaz | Popis |
|--------|-------|
| `create_project_views.py` | Playwright automatizace views (vyzaduje `playwright`) |

---

## Architektura

```
GitHub Projects (UI)  <-->  .edpa/ item files (Git)
       |                          |
  PM/BO pracuji            Verzovane, auditovatelne
       |                          |
  Issue Types (org)        EDPA engine (vypocet)
       |                          |
  Custom fields            Reports + Snapshots
```

### Tok dat

```
                    +---------------------------+
                    |    GitHub Projects (UI)    |
                    |  PM/BO spravuji backlog    |
                    +---------------------------+
                         |              ^
           sync pull     |              |     sync push
         (cron 15min)    v              |   (push trigger)
                    +---------------------------+
                    |  .edpa/ item files (Git)   |
                    |  Source of truth           |
                    +---------------------------+
                              |
                    +---------+---------+
                    |                   |
              +----------+       +----------+
              |  Engine  |       |  Backlog |
              | (vypocet)|       |  CLI     |
              +----------+       +----------+
                    |                   |
              +----------+       +----------+
              | Reports  |       |  WSJF    |
              | Snapshots|       |  Tree    |
              | Vykazy   |       |  Validate|
              +----------+       +----------+
```

### Evidence detection

EDPA detekuje prispevky z techto Git signaluov:

| Signal | Vaha | Evidence role |
|--------|------|--------------|
| GitHub issue assignee | 4.0 | owner |
| `/contribute @person weight:X` | 3.0 | key |
| PR author referencing item | 2.0 | key |
| Commit author s S-XXX/F-XXX | 1.0 | reviewer |
| PR reviewer | 1.0 | reviewer |
| Issue/PR komentar | 0.5 | consulted |

Nejvyssi signal urcuje evidence role (signaly se nescitaji).

### Vypocet EDPA (simple mode)

Pro kazdou osobu v iteraci:

1. Detekovat evidence na kazde polozce
2. Pro kazdy par (osoba, polozka): `score = JS x CW`
3. Pro kazdou osobu: `ratio_i = score_i / sum(scores)`
4. Odvozene hodiny: `hours_i = ratio_i x capacity`

Invariant: `sum(hours) = capacity` (presne, ne priblizne).

---

## Troubleshooting

### gh auth -- chybejici scopes

```
ERROR: insufficient scopes for organization query
```

**Reseni:**

```bash
gh auth refresh -s repo,project,read:project,admin:org
gh auth status  # overit
```

### Issue Types -- "Not Found" pri setup

```
ERROR: Organization not found or insufficient permissions
```

**Reseni:**
- Overit ze jste clen organizace s admin pravami
- Issue Types vyzaduji org-level pristup (ne personal account)
- `gh auth refresh -s admin:org`

### Backlog validate -- chyby

```
ERROR: S-200 references non-existent feature F-999
```

**Reseni:**
- Overit ze vsechny `feature:` reference v stories ukazuji na existujici features
- Kazda story musi mit parent feature
- Kazda feature musi mit parent epic

```
WARNING: S-200 Job Size exceeds maximum (JS=13, max=8)
```

**Reseni:**
- Story JS max 8 (classic 2/10) nebo 5 (AI-native 1/5)
- Rozdelit velkou story na mensi

### EDPA engine -- invariant failure

```
INVARIANT FAILURE -- check results
All invariants passed: NO
```

**Mozne priciny:**
- Osoba nema zadne evidence (neni assignee, zadne commity)
- Vsechny CW jsou 0 (zadna evidence nad threshold)
- Kapacita je 0

**Reseni:**
- Overit ze kazda osoba ma alespon 1 prirazeny work item
- Overit ze commity/PR referuji spravne item ID (S-XXX, F-XXX)
- Overit `.edpa/config/people.yaml` -- kapacity > 0

### Sync -- konflikty

```
CONFLICT: S-200 modified in both Git and Projects
```

**Reseni:**

```bash
# Zobrazit konflikty
python .claude/edpa/scripts/sync.py conflicts

# Diff -- co by se zmenilo
python .claude/edpa/scripts/sync.py diff
```

Rucne vyresit v prislusnem item souboru v `.edpa/`, pak:

```bash
python .claude/edpa/scripts/sync.py push
```

### Sync -- loop prevence

Workflow `sync-git-to-projects.yml` obsahuje:

```yaml
if: github.actor != 'github-actions[bot]'
```

To zabranuje nekonecne smycce: push -> sync -> push -> sync...

### GitHub Project -- custom fields chybi

```
ERROR: Field "Job Size" not found on project
```

**Reseni:**
- Spustit znovu `project_setup.py` (vytvori chybejici fields)
- Nebo rucne: Settings -> Custom fields -> Add field

### Branch naming CI failure

```
Branch name does not follow EDPA convention.
Required format: {type}/{item-id}-{description}
```

**Reseni:**
- Format: `feature/S-200-omop-parser`, `bugfix/S-215-fix-validation`
- Typ: `feature`, `bugfix`, `hotfix`, `chore`
- Prefix: `S` (Story), `F` (Feature), `E` (Epic), `T` (Task), `B` (Bug)
- `main`, `develop`, `release/*` jsou vyjimky (prochazi bez kontroly)

### Python -- chybejici PyYAML

```
ERROR: PyYAML required. Install with: pip install pyyaml
```

**Reseni:**

```bash
pip install pyyaml
# Nebo v GitHub Actions (uz je v workflow):
# pip install pyyaml openpyxl
```

### Iteration close -- "config not found"

```
ERROR: .edpa/config/people.yaml not found. Run EDPA setup first.
```

**Reseni:**
- Templates jsou v `.claude/edpa/templates/*.tmpl` -- musi se zkopirovat:

```bash
cp .claude/edpa/templates/people.yaml.tmpl .edpa/config/people.yaml
cp .claude/edpa/templates/heuristics.yaml.tmpl .edpa/config/heuristics.yaml
cp .claude/edpa/templates/project.yaml.tmpl .edpa/config/project.yaml
```

- Soubory v `.edpa/config/*.yaml` (ne `*.yaml.tmpl`) musi byt commitnute v repu

### MAD prilis vysoke (> 0.10)

**Mozne priciny:**
- Strategicke role (BO, PM, Arch) maji systematicky nizsi auto-CW nez realitu
- Git meri jen commity/PR, ne rozhodovani, specifikaci, mentoring

**Reseni:**
1. Analyzovat zaznamy s nejvetsim `abs(auto_cw - confirmed_cw)`
2. Seskupit dle role
3. Pokud BO ma konzistentne vyssi confirmed_cw -> zvysit `role_overrides.BO.consulted`
4. Pokud Arch reviewer je podhodnocen -> zvysit `role_overrides.Arch.reviewer`
5. Znovu evaluovat

### Playwright views -- prihlaseni

```
ERROR: Login timeout
```

**Reseni:**
- Prvni spusteni vyzaduje manualni prihlaseni v prohlizeci
- Prohlizec se otevre automaticky
- Po prihlaseni se session ulozi do `~/.edpa/playwright-profile`
- Dalsi spusteni uz prihlaseni nevyzaduji

---

## Slovnicek

| Termin | Vyznam |
|--------|--------|
| **PI** | Planning Interval (10 tydnu = 4 delivery + 1 IP iterace) |
| **IP** | Innovation & Planning (posledni iterace PI) |
| **JS** | Job Size -- relativni velikost prace (Fibonacci) |
| **BV** | Business Value -- obchodni hodnota |
| **TC** | Time Criticality -- casova kritickost |
| **RR** | Risk Reduction -- snizeni rizika |
| **WSJF** | Weighted Shortest Job First = (BV+TC+RR)/JS |
| **CW** | Contribution Weight -- vaha prispevku (0.0 - 1.0) |
| **RS** | Role Strength -- sila role (volitelne v full mode) |
| **MAD** | Mean Absolute Deviation -- prumerna absolutni odchylka |
| **Evidence** | Doklad o praci (commit, PR, assignee, komentar) |
| **Ground truth** | Potvrzena realita od tymu (pro kalibraci) |
