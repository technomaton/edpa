# EDPA Playbook -- Od nuly po prvni PI

Kompletni prirucka pro nasazeni metodiky EDPA (Evidence-Driven Proportional Allocation) na novy projekt. Od prazdneho repozitare po uzavreni prvniho Planning Intervalu a kalibraci signalu.

EDPA V2 je **local-first**: zdrojem pravdy je `.edpa/backlog/**/*.md` (YAML frontmatter), git je audit trail. GitHub je **volitelny** -- zadny GitHub Project, zadne org Issue Types, zadny obousmerny sync.

**Verze:** EDPA 2.5.1
**Posledni aktualizace:** 2026-06-01

---

## Obsah

1. [Prerekvizity](#prerekvizity)
2. [Faze 1: Infrastruktura (Den 1)](#faze-1-infrastruktura-den-1-1-hodina)
3. [Faze 2: Prvni iterace (Tyden 1)](#faze-2-prvni-iterace-tyden-1)
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
| Python | 3.10+ | `python3 --version` |
| pyyaml + openpyxl + ruamel.yaml | libovolna | `pip install pyyaml openpyxl ruamel.yaml` |
| Git | 2.30+ | `git --version` |
| GitHub CLI (gh) | 2.40+ | `gh --version` -- **volitelne** |

EDPA V2 bezi cisty lokalne nad gitem. `gh` je potreba **pouze** pokud chcete volitelny PR-signal sync (workflow `edpa-contribution-sync.yml`) -- viz [Volitelny GitHub](#volitelny-github-pr-signal-sync).

### Volitelne: GitHub CLI scopes pro PR-signal sync

Pokud zapnete volitelny PR-signal sync, staci bezne `repo` scope:

```bash
gh auth login        # bezny repo scope staci
gh auth status
```

> Org-level scopy (`admin:org`, `project`) z EDPA V1 uz **nejsou potreba** -- v 2.0.0 zmizely GitHub Projecty i org Issue Types.

### Tym a backlog

Pred zacatkem je treba mit:

- Definovany tym: jmena, role (Arch, Dev, DevSecOps, PM, QA, BO), FTE, kapacity
- Alespon zakladni backlog (1 Epic, 2-3 Features, 5-10 Stories)
- Git repozitar (GitHub remote je volitelny)

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

## Faze 1: Infrastruktura (Den 1, ~1 hodina)

### Cesta A: Claude Code (doporuceno)

V terminalu s Claude Code nainstalovanym:

```
/edpa:setup --with-ci --with-hooks --with-rules
```

Claude Code (skill `/edpa:setup`) provede kroky 1.1-1.4 automaticky -- vendoruje engine do `.edpa/engine/`, naseje konfiguraci a `id_counters.yaml`, a volitelne nainstaluje git hooky, PR-signal CI workflow a `.claude/rules/`. Idempotentni -- opakovane spusteni nic nerozbije. `--with-hooks` je lefthook-aware (pri pritomnem `lefthook.yml` vypise snippet misto zapisu do `.git/hooks/`); stav overis pres `--check-hooks`.

### Cesta B: Manualni CLI

Nasledujici kroky popisuji manualni postup bez Claude Code.

### 1.1 Nainstalovat EDPA a vendorovat engine

**Varianta A: Shell installer (doporuceno)**

```bash
cd my-project
curl -fsSL https://edpa.technomaton.com/install.sh | sh
```

**Varianta B: project_setup.py**

`project_setup.py` vendoruje engine + nasaze configy + `id_counters.yaml`. Flagy navic nainstaluji git hooky, contribution-sync CI workflow a `.claude/rules/`. Bez `--org`/`--repo` -- zadne GitHub provisioning.

```bash
python3 .edpa/engine/scripts/project_setup.py --with-ci --with-hooks --with-rules
```

> `--with-hooks` je lefthook-aware (pri pritomnem `lefthook.yml` vypise paste-ready snippet misto zapisu do `.git/hooks/`); stav hooku overis pres `--check-hooks`.

Vysledna struktura:

```
my-project/
  .edpa/
    config/
      edpa.yaml          # Projekt + governance (zdroj verze metodiky)
      people.yaml        # Tym a kapacity (teams, people)
      cw_heuristics.yaml # CW signalove vahy
      id_counters.yaml   # Citace ID (S-1, E-1, F-1, ...)
    backlog/
      initiatives/       # 1 soubor = 1 initiative (.md s YAML frontmatter)
      epics/             # 1 soubor = 1 epic
      features/          # 1 soubor = 1 feature
      stories/           # 1 soubor = 1 story
    iterations/          # PI a iterace (PI-2026-1.yaml, PI-2026-1.1.yaml, ...)
    reports/             # Generovane reporty + edpa_results.json per iterace
    snapshots/           # Zmrazene snapshoty iteraci
    data/                # Ground truth pro kalibraci (po PI)
    engine/              # VENDOROVANY engine (instaluje project_setup.py)
      VERSION
      scripts/
        engine.py            # EDPA vypocetni jadro
        backlog.py           # Sprava backlogu (add, tree, show, wsjf, validate)
        detect_contributors.py  # evidence[] -> contributors[] (cw)
        calibrate_signals.py    # Kalibrace signalovych vah (MAD)
        reports.py           # Vykazy + PI summary + xlsx
        board.py             # Lokalni HTML Kanban board
        capacity_override.py # Kapacitni override per osoba/iterace
        sync_pr_contributions.py  # Materializace PR-thread signalu (volitelne CI)
        ...                  # dalsi pomocne skripty + hooks/
      templates/
        people.yaml.tmpl
        cw_heuristics.yaml.tmpl
        edpa.yaml.tmpl
  .github/workflows/         # JEN s --with-ci
    edpa-contribution-sync.yml  # Po merge PR: PR-thread signaly -> evidence[]
  .claude/rules/             # JEN s --with-rules (architektonicka pravidla)
  docs/                      # Dokumentace
```

> **V2 cesty:** user-facing engine je vendorovany v `.edpa/engine/scripts/*.py` (NE `.claude/edpa/scripts/`, NE `plugin/edpa/scripts/`). Sablony v `.edpa/engine/templates/`.

### 1.2 Nakonfigurovat tym a kapacity (people.yaml)

`project_setup.py` uz `.edpa/config/people.yaml` naseje ze sablony. Pripadne rucne:

```bash
cp .edpa/engine/templates/people.yaml.tmpl .edpa/config/people.yaml
```

Upravit `.edpa/config/people.yaml`. Tady ziji **teams + people** -- zadny separatni registr. Kadence (iteration_weeks / pi_iterations) se nastavuje per-PI v `pi:` bloku `.edpa/iterations/PI-*.yaml`, pripadne se odvodi z `weeks:`/dat iteraci -- viz [cadence.md](cadence.md):

```yaml
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

**Dulezite:** `planning_factor` je planovaci heuristika (planujeme na 80%). EDPA engine pocita vzdy se 100% kapacity -- buffer absorbuje neplanovane prace. Pole `github:` u osoby je volitelne -- pouziva ho jen volitelny PR-signal sync k mapovani GH login -> `people[].id`.

> **V2 pozn.:** neexistuje zadny separatni `registry`/`capacity` soubor. Cely tym a kapacity zijou v `people.yaml`. (V1 dokumentace tu omylem uvadela `people.yaml` dvakrat -- opraveno.)

### 1.3 Nakonfigurovat projekt + governance (edpa.yaml)

`project_setup.py` naseje `.edpa/config/edpa.yaml` ze sablony (NE `project.yaml` -- ten v V2 neexistuje). Pripadne rucne:

```bash
cp .edpa/engine/templates/edpa.yaml.tmpl .edpa/config/edpa.yaml
```

Upravit `.edpa/config/edpa.yaml`:

```yaml
project:
  name: "Muj Projekt"                   # ← Display name (jedine povinne pole)
  description: ""
  domain: "mujprojekt.cz"
  # Volitelne: funding (granty/dotace) + organizations (pro audit/fakturaci)

governance:
  # Auto-razitkovano na verzi pluginu instalatorem.
  methodology: "EDPA 2.5.1"
  # Jedina vypocetni cesta od v1.14 (zadny simple/full/gates mode selector,
  # zadny audit_mode -- snapshoty vzdy nesou plny signals[] audit trail).

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
    defect: "D"
    event: "EV"
```

> **Odstraneno v 2.0.0:** pole `calculation_mode` (simple/full) a `audit_mode`. Engine ma jedinou vypocetni cestu (JS x CW) a snapshoty vzdy nesou plny audit trail.

### 1.4 Nakonfigurovat CW signalove vahy (cw_heuristics.yaml)

`project_setup.py` naseje `.edpa/config/cw_heuristics.yaml` (NE `heuristics.yaml`). Pripadne rucne:

```bash
cp .edpa/engine/templates/cw_heuristics.yaml.tmpl .edpa/config/cw_heuristics.yaml
```

Vychozi hodnoty jsou kalibrovane Monte Carlo simulaci. Pro zacatek staci bez uprav. Kalibrace na vlastni data se provadi po prvnim PI (viz [Faze 3](#33-kalibrace-cw-signalu)).

EDPA V2 je **evidence-driven**: `cw[osoba, item] = contribution_score / Σ contribution_score`, kde `contribution_score = Σ signal_weight`. Klicove vychozi signalove vahy:

| Signal | Vaha | Popis |
|--------|------|-------|
| `assignee` | 4.00 | GitHub issue assignee / owner |
| `pr_author` | 3.40 | Autor PR referujici item |
| `commit_author` | 2.78 | Commit s ID v branchi/title/zprave |
| `pr_reviewer` | 2.25 | Odeslany PR review (mimo self) |
| `issue_comment` | 1.14 | Komentar na issue/PR (mimo boty) |

Rolove vahy prispevatelu (`--contributor PERSON:ROLE:CW`) -- owner 1.0 / key 0.6 / reviewer 0.25 / consulted 0.15; `evidence_threshold` 1.0. `cw_heuristics.yaml` navic obsahuje `gate_weights` pro Feature/Epic/Initiative -- status transition na rodici rozdeluje jeho Job Size napric lifecyclem (souc = 1.0 per typ).

### 1.5 Nakonfigurovat iterace (iterations/)

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

> **Tip:** PI-level soubor (`pi:`) nemusíš psát ručně — založ ho příkazem
> `/edpa:create-pi PI-2026-1` (nebo MCP nástrojem `edpa_pi_create`). Validuje
> id, odmítne přepis a commitne. Per-iteration
> soubory přidávej přes `edpa_iteration_create`. Pozor: přípona musí být
> `.yaml`, ne `.yml` — loader `.yml` tiše ignoruje.

> **Odstraneno v 2.0.0:** sync blok (`github_org`, `github_project_number`, `sync_interval`) -- V2 je local-first, zadny GitHub Project se neprovisionuje.

### 1.6 Naplnit backlog

EDPA pouziva file-per-item strukturu -- kazdy work item je samostatny **`.md` soubor s YAML frontmatter** (v V2 NE `.yaml`):

```
.edpa/
  config/
    edpa.yaml                    # projekt + governance
    people.yaml                  # tym a kapacity
    cw_heuristics.yaml           # CW signalove vahy
    id_counters.yaml             # citace ID
  backlog/
    initiatives/
      I-1.md                     # 1 soubor = 1 initiative
    epics/
      E-1.md                     # 1 soubor = 1 epic
    features/
      F-1.md                     # 1 soubor = 1 feature
    stories/
      S-1.md                     # 1 soubor = 1 story
  iterations/
    PI-2026-1.1.yaml             # plan iterace
```

Priklad story souboru (`.edpa/backlog/stories/S-1.md` -- YAML frontmatter + volitelne telo):
```markdown
---
id: S-1
type: Story
title: "Implementace parseru"
status: Backlog
parent: F-1
js: 5
assignee: bob
iteration: PI-2026-1.1
---
Volitelny popis / akceptacni kriteria v Markdownu.
```

Pridani noveho itemu (LOKALNE -- zadne GitHub volani):
```bash
# Claude Code:
/edpa:add    # interaktivne prida jeden item (Initiative/Epic/Feature/Story/Defect/Event/Risk)

# CLI:
python3 .edpa/engine/scripts/backlog.py add --type Story --parent F-1 \
  --title "..." --js 5 --assignee bob --iteration PI-2026-1.1
python3 .edpa/engine/scripts/backlog.py add --type Epic --parent I-1 \
  --title "..." --js 13 --bv 13 --tc 8 --rr-oe 5
```

`backlog.py add` je v V2 **cisty lokalni** (zadne `gh`): ID se prideli z `id_counters.yaml` (`S-42`, `E-15`, `I-3`), hierarchie rodice se zvaliduje, YAML se zapise pod `.edpa/backlog/` a zmena se auto-commitne jako `feat(<ID>):`. PR-odvozene signaly prichazeji az pozdeji pres volitelny contribution-sync workflow.

> **Odstraneno v 2.0.0:** "GH-first" rezim `add` (tvorba GH issue, sub-issue API, prepis title na `"{ID}: {title}"`). V V2 je `add` local-only -- V1 tvrzeni "strictly GH-first" uz NEPLATI.

Pridelovani prispevatelu lze udelat hned pri zalozeni (per-item CW share):
```bash
python3 .edpa/engine/scripts/backlog.py add --type Story --parent F-1 --title "..." --js 5 \
  --contributor bob:owner:0.7 --contributor carol:reviewer:0.3
# Format PERSON:ROLE:CW, ROLE ∈ {owner,key,reviewer,consulted}, CW ∈ [0,1]
```

Overit integritu:

```bash
python3 .edpa/engine/scripts/backlog.py validate
```

Zobrazit hierarchii:

```bash
python3 .edpa/engine/scripts/backlog.py tree
python3 .edpa/engine/scripts/backlog.py tree --level epic
```

Zobrazit WSJF prioritizaci:

```bash
python3 .edpa/engine/scripts/backlog.py wsjf
python3 .edpa/engine/scripts/backlog.py wsjf --level feature
```

Zobrazit detail polozky:

```bash
python3 .edpa/engine/scripts/backlog.py show S-1
python3 .edpa/engine/scripts/backlog.py show E-1
```

### 1.7 Overit setup

```bash
# Demo EDPA engine (bez realnych dat)
python3 .edpa/engine/scripts/engine.py --demo

# Validace backlogu
python3 .edpa/engine/scripts/backlog.py validate

# Status projektu
python3 .edpa/engine/scripts/backlog.py status

# Vizualni HTML board (local-first nahrada za Projects board)
python3 .edpa/engine/scripts/board.py --output .edpa/board.html
```

### 1.8 Commitnout zakladni konfiguraci

`backlog.py add` commituje itemy automaticky. Pocatecni config a vendorovany engine commitni:

```bash
git add .edpa/
git commit -m "feat(edpa): initial EDPA V2 setup for my-project"
git push origin main   # volitelne, pokud mate GitHub remote
```

> **Odstraneno v 2.0.0:** §1.6 Issue Types (`issue_types.py setup --org`), §1.8 GitHub Project (`project_setup.py --org/--repo/--project-title`, custom fields, sub-issues), §1.9 Project views (`project_views.py`, `create_project_views.py`, Playwright). V2 nahrazuje board view lokalnim `board.py` / `/edpa:board`.

---

## Faze 2: Prvni iterace (Tyden 1)

### 2.1 Iteration Planning

1. **Potvrzeni kapacity** -- tym potrdi dostupnost na iteraci
2. **Vyber stories** -- z backlogu dle WSJF poradi, na 80% kapacity

```bash
# WSJF ranking features
python3 .edpa/engine/scripts/backlog.py wsjf --level feature

# Tree pro konkretni iteraci
python3 .edpa/engine/scripts/backlog.py tree --iteration PI-2026-1.1
```

3. **Prirazeni assignees** -- kazda story musi mit assignee
4. **Aktualizace backlogu** -- `iteration: PI-2026-1.1` na vybranych stories

### 2.2 Denni prace

**Branch naming konvence** `{type}/{ITEM}-{popis}` -- v V2 ji vynucuji **git hooky** (`--with-hooks`), uz ne CI:

```bash
# Format: {type}/{ITEM_ID}-{popis}
git checkout -b feature/S-200-omop-parser
git checkout -b feature/F-102-anon-engine
git checkout -b bugfix/S-215-upload-validation
git checkout -b chore/T-050-ci-pipeline
```

Povolene typy: `feature`, `bugfix`, `hotfix`, `chore`
Povolene prefixy: `S` (Story), `F` (Feature), `E` (Epic), `T` (Task), `D` (Defect), `I` (Initiative), `EV` (Event)

**Git hooky (`--with-hooks`)** materializuji evidenci lokalne, bez GitHubu:

| Hook | Co dela |
|------|---------|
| pre-commit | ID safety -- kontrola referenci |
| commit-msg | Vyzaduje referenci itemu nebo `no-ticket:` |
| post-commit | Zaznamenava `commit_author` evidence |
| pre-push | Kontrola ID kolizi vuci remote |

Registrace je idempotentni a sebe-obnovujici: EDPA znacka sve hooky sentinelem `EDPA-MANAGED-HOOK`, opakovany `--with-hooks` (nebo `--refresh-hooks`) je osvezi a cizi (ne-EDPA) hook v dane pozici **nikdy nepreplacne** -- vypise hlasku + radek k rucnimu zaretezeni (`sh .edpa/engine/scripts/hooks/<hook> "$@"`). Pokud je v repu **lefthook** (`lefthook.yml`), `.git/hooks/` vlastni lefthook, takze EDPA tam nezapisuje a misto toho vypise hotovy snippet do `lefthook.yml`; pote spust `lefthook install`. Stav hooku overis read-only pres `--check-hooks` (kazdy hook jako active / missing / foreign, pripadne flag lefthook).

```yaml
# lefthook.yml -- EDPA hooky (pre-push MUSI mit use_stdin: true, jinak push zatuhne)
pre-commit:
  commands:
    edpa-id-safety:
      run: sh .edpa/engine/scripts/hooks/pre-commit-id-safety
commit-msg:
  commands:
    edpa-ticket-attached:
      run: sh .edpa/engine/scripts/hooks/commit-msg-ticket-attached {1}
post-commit:
  commands:
    edpa-evidence:
      run: sh .edpa/engine/scripts/hooks/post-commit-evidence
pre-push:
  commands:
    edpa-id-safety:
      run: sh .edpa/engine/scripts/hooks/pre-push-id-safety {1} {2}
      use_stdin: true
```

**Commit konvence:**

```bash
git commit -m "feat(S-200): implement OMOP CDM parser"
git commit -m "fix(S-215): validate upload file size"
git commit -m "test(S-201): add unit tests for parser"
git commit -m "docs(E-10): update epic hypothesis"
```

EDPA engine rozpoznava reference `S-XXX`, `F-XXX`, `E-XXX` v commitech (a volitelne v PR) pro detekci evidence.

**Pull Request workflow (volitelne, jen s GitHub remote):**

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

PR review = signal pro EDPA. Aby se PR-thread signaly (`pr_reviewer`, `issue_comment`) dostaly do `evidence[]`, je potreba volitelny contribution-sync workflow -- viz [2.3](#23-volitelny-github-pr-signal-sync).

### 2.3 Volitelny GitHub PR-signal sync

EDPA V2 funguje cisty lokalne -- engine cte evidenci z gitu (`commit_author`) + YAML edits (`yaml_edit`) + gate transitions. GitHub je **volitelny** a slouzi pouze k materializaci PR-thread signalu.

S `--with-ci` se nainstaluje **jediny** V2 workflow `.github/workflows/edpa-contribution-sync.yml`. Po merge PR spusti `sync_pr_contributions.py`, ktery z PR-threadu vytahne signaly (`pr_reviewer`, `issue_comment`) a zapise je do `evidence[]` prislusnych itemu. Vyzaduje secret `EDPA_TOKEN` (viz `docs/edpa-token-setup.md`). Flow metriky lze cist pres MCP nastroj `edpa_flow_metrics`.

> **Odstraneno v 2.0.0:** obousmerny sync `sync.py` (pull/push/diff/status/conflicts/`--mock`) -- v V2 **neexistuje**. Stejne tak workflow `edpa-sync-projects-to-git.yml` a `edpa-sync-git-to-projects.yml`. Zadny GitHub Project se nepropaguje. Pro board pouzij lokalni `/edpa:board`.

### 2.4 Iteration Close

Na konci kazde iterace (1 tyden AI-native / 2 tydny classic):

**Claude Code (doporuceno):**

```
/edpa:close-iteration PI-2026-1.1
```

Claude Code (skill `close-iteration`) pripravi kapacitu, spusti EDPA engine a vygeneruje reporty automaticky.

**Manualni CLI:**

```bash
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.1
# volitelne: --output cesta/edpa_results.json
```

**Vystupy:**

```
.edpa/reports/iteration-PI-2026-1.1/
  edpa_results.json        # Kompletni vypocet (JSON)
  timesheet-alice.md       # Vykaz pro kazdou osobu (DerivedHours > 0)
  timesheet-team.md        # Agregovany tymovy rollup
  edpa-results.xlsx        # Team Summary + Item Costs (Excel)
.edpa/snapshots/
  PI-2026-1.1.json         # Zmrazeny snapshot (audit trail)
```

> **Pozn.:** per-person soubory jsou `timesheet-<id>.md` (v V2 uz NE `vykaz-*.md`).

**Vypocet** (od v1.14 jedina cesta): `score = JS x CW`, `hours = (score / Σ score) x capacity`. Zadny `--mode simple|full` ani Role Strength.

**Invarianty** (engine automaticky kontroluje):

- Soucet `DerivedHours` osoby == jeji kapacita (presne)
- Soucet pomeru == 1.0
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
/edpa:calibrate
```

Claude Code (skill `/edpa:autocalib`) spusti kalibraci signalovych vah pres Monte Carlo + coordinate-descent optimalizator, vyhodnoti MAD a navrhne upravy `cw_heuristics.yaml`. Pro generovani reportu:

```
/edpa:reports PI-2026-1
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

**Doporuceni:** Zaznamenat alespon 20 zaznamu (minimum pro kalibraci). Idealne 30-50 pro statistickou relevanci.

### 3.3 Kalibrace CW signalu

```bash
python3 .edpa/engine/scripts/calibrate_signals.py \
  --ground-truth .edpa/data/ground_truth.yaml \
  --heuristics .edpa/config/cw_heuristics.yaml
```

`calibrate_signals.py` (skill `/edpa:calibrate`) jede dvoufazove: nahodny Monte Carlo sample napric signalovymi vahami -> coordinate-descent (Nelder-Mead) zjemneni kolem nejlepsich kandidatu. Metrika je MAD na synteticikem korpusu; nizsi MAD = lepsi kalibrace.

Vystup (orientacne):

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
| 0.06 - 0.10 | Prijatelne | Zvazit upravu signalovych vah |
| > 0.10 | Spatne | Nutna kalibrace |

**Korekce signalovych vah:**

Pokud MAD > 0.06, analyzovat kde jsou nejvetsi odchylky:

1. Podivat se na zaznamy kde `abs(auto_cw - confirmed_cw)` je nejvyssi
2. Identifikovat vzory dle role (typicky BO, PM, Arch -- strategicke role jsou Gitem podhodnoceny)
3. Upravit `signals:` vahy v `.edpa/config/cw_heuristics.yaml`
4. Znovu spustit kalibraci

> **Odstraneno v 2.0.0:** `evaluate_cw.py` (nahrazeno `calibrate_signals.py` / `/edpa:calibrate`) a soubor `heuristics.yaml` (nahrazeno `cw_heuristics.yaml`).

### 3.4 Planovani dalsiho PI

1. **Nove epicy/features** -- pridat pres `backlog.py add` (auto-commit) do `.edpa/backlog/`
2. **WSJF prioritizace:**

```bash
python3 .edpa/engine/scripts/backlog.py wsjf
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
/edpa:close-iteration PI-2026-1.X    # uzavreni iterace
/edpa:reports PI-2026-1.X             # generovani reportu
```

Kazdy PI:

```
/edpa:calibrate                       # kalibrace signalovych vah
```

### Manualni postup

### Kazda iterace (1 tyden AI-native / 2 tydny classic)

1. **Planning** -- vybrat stories, prirazit assignees
2. **Denni prace** -- branch naming, commity s referencemi, (volitelne) PR review
3. **Iteration Close** -- EDPA engine, generovani reportu
4. **Review** -- tym zkontroluje vykazy, zahlasi korektury (manualni CW override pres `--contributor` / `/contribute`)

### Kazdy PI (5 tydnu AI-native / 10 tydnu classic)

1. **Retrospektiva** -- auto-detected CW vs realita
2. **Ground truth** -- zaznamenat alespon 20 novych zaznamu
3. **CW kalibrace** -- `calibrate_signals.py`, vyhodnotit MAD
4. **Velocity trend** -- porovnat delivery across iteraci
5. **Predictability** -- (delivered_sp / planned_sp) across iteraci

```bash
# Status za celou iteraci
python3 .edpa/engine/scripts/backlog.py status --iteration PI-2026-1.3

# Celkovy status projektu
python3 .edpa/engine/scripts/backlog.py status

# Kapacitni override (napr. dodatecne hodiny mimo evidenci)
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.1 --add --person bob --hours 12

# Velocity / flow reporty
python3 .edpa/engine/scripts/reports.py PI-2026-1.1
```

### Volitelna automatizace pres GitHub Actions

V2 ma **jediny** volitelny workflow (jen s `--with-ci`):

| Workflow | Trigger | Co dela |
|----------|---------|--------|
| `edpa-contribution-sync.yml` | po merge PR | `sync_pr_contributions.py` materializuje PR-thread signaly (`pr_reviewer`, `issue_comment`) do `evidence[]` |

> **Odstraneno v 2.0.0:** `edpa-branch-check.yml`, `edpa-iteration-close.yml`, `edpa-sync-projects-to-git.yml`, `edpa-sync-git-to-projects.yml`. Branch konvenci nyni hlida lokalni git hook, iteration close se spousti lokalne, obousmerny sync neexistuje.

---

## Checklist -- Co mit hotove

### Den 1

- [ ] Engine vendorovany do `.edpa/engine/` (`/edpa:setup` nebo `project_setup.py`)
- [ ] `.edpa/config/people.yaml` -- tym s rolemi, FTE, kapacitami (teams + people)
- [ ] `.edpa/config/edpa.yaml` -- nazev projektu, governance, naming
- [ ] `.edpa/config/cw_heuristics.yaml` -- vychozi signalove vahy (ze sablony)
- [ ] `.edpa/config/id_counters.yaml` -- naseto
- [ ] `.edpa/iterations/` -- PI + iterace s datumy
- [ ] Backlog naplneny pres `backlog.py add` (alespon 1 Epic, 3 Features, 10 Stories)
- [ ] `backlog.py validate` projde bez chyb
- [ ] `engine.py --demo` projde uspesne
- [ ] (volitelne) git hooky nainstalovany (`--with-hooks`) a overeny (`--check-hooks` -> vsechny active; pri lefthooku snippet v `lefthook.yml` + `lefthook install`), contribution-sync CI (`--with-ci`)

### Tyden 1

- [ ] Tym pracuje s branch naming konvenci (`feature/S-XXX-popis`)
- [ ] Commity referuji work items (`feat(S-XXX): ...`)
- [ ] post-commit hook zaznamenava `commit_author` evidenci (overeno `--check-hooks`; je-li post-commit `missing`/`foreign`, contribution evidence se tise nezapisuji -- u lefthooku doplnit snippet + `lefthook install`)
- [ ] (volitelne) PR reviews probihaji a contribution-sync je materializuje

### Konec iterace 1

- [ ] EDPA engine spusten pro iteraci
- [ ] `edpa_results.json` vygenerovan v `.edpa/reports/iteration-<ID>/`
- [ ] Vykazy `timesheet-<id>.md` vygenerovany (per-person)
- [ ] Vsechny invarianty prosly (`all_invariants_passed: true`)
- [ ] Snapshot zmrazen v `.edpa/snapshots/`
- [ ] Tym zkontroloval vysledky

### Konec iterace 2-4

- [ ] Velocity stabilni (odchylka < 20%)
- [ ] Prediktabilita > 80% (delivered / planned)

### Konec PI 1

- [ ] Ground truth zaznamenano (min. 20 zaznamu)
- [ ] CW kalibrace provedena (`calibrate_signals.py` / `/edpa:calibrate`)
- [ ] MAD vyhodnoceno (cil: < 0.06)
- [ ] Signalove vahy upraveny v `cw_heuristics.yaml` (pokud MAD > 0.06)
- [ ] Planovani PI 2 -- nove epicy, WSJF, kapacity
- [ ] Nove iteration soubory v `.edpa/iterations/` pro novy PI

---

## CLI Reference

> Vsechny skripty bezi z vendorovaneho engine: `python3 .edpa/engine/scripts/<skript>.py`.

### Claude Code prikazy (doporuceno)

| Prikaz | Popis |
|--------|-------|
| `/edpa:setup --with-ci --with-hooks --with-rules` | Vendoruje engine, naseje configy + id_counters, volitelne hooky/CI/rules |
| `/edpa:add` | Prida backlog item (lokalne, auto-commit) |
| `/edpa:close-iteration PI-2026-1.X` | Uzavreni iterace -- kapacita, EDPA engine, reporty |
| `/edpa:reports PI-2026-1.X` | Generovani vykazu a PI summary |
| `/edpa:board` | Vizualni HTML Kanban board (lokalni) |
| `/edpa:calibrate` | Kalibrace signalovych vah -- MAD, navrh uprav `cw_heuristics.yaml` |

### engine.py -- EDPA vypocetni jadro

| Prikaz | Popis |
|--------|-------|
| `engine.py --demo` | Demo s ukázkovymi daty |
| `engine.py --edpa-root .edpa --iteration PI-2026-1.3` | Plny EDPA vypocet pro iteraci (cte backlog/config/heuristiky z `.edpa`) |
| `engine.py --edpa-root .edpa --iteration ID --output cesta/edpa_results.json` | Vlastni vystupni cesta |
| `engine.py --status` | Stav konfigurace |

### backlog.py -- Sprava backlogu

| Prikaz | Popis |
|--------|-------|
| `backlog.py add --type Story --parent F-1 --title "..." --js 5 --assignee bob --iteration PI-2026-1.1` | Prida item lokalne (ID z id_counters.yaml, auto-commit `feat(<ID>):`) |
| `backlog.py add --type Epic --parent I-1 --title "..." --js 13 --bv 13 --tc 8 --rr-oe 5` | Prida Epic s WSJF metrikami |
| `backlog.py add ... --contributor PERSON:ROLE:CW` | Prida prispevatele (owner/key/reviewer/consulted, CW ∈ [0,1]) |
| `backlog.py tree` | Zobrazí plnou hierarchii (I -> E -> F -> S) |
| `backlog.py tree --level epic\|feature\|story` | Filtr na uroven |
| `backlog.py tree --iteration PI-2026-1.1` | Filtr stories na iteraci |
| `backlog.py show S-1` | Detail polozky |
| `backlog.py status [--iteration PI-2026-1.1]` | Status projektu / iterace |
| `backlog.py wsjf [--level feature]` | WSJF prioritizace |
| `backlog.py validate` | Kontrola integrity backlogu |

### reports.py -- Vykazy a PI summary

| Prikaz | Popis |
|--------|-------|
| `reports.py PI-2026-1.1` | Per-person `timesheet-<id>.md` + `timesheet-team.md` + xlsx |
| `reports.py --pi PI-2026-1` | Agregace vsech iteraci pod PI |
| `reports.py PI-2026-1.1 --out cesta/` | Vlastni vystupni adresar |

### board.py -- Lokalni HTML board

| Prikaz | Popis |
|--------|-------|
| `board.py --output .edpa/board.html` | Vygeneruje Kanban board z `.edpa/backlog/` |
| `board.py --iteration PI-2026-1.4 --open` | Filtr na iteraci + otevre v prohlizeci |

### capacity_override.py -- Kapacitni override

| Prikaz | Popis |
|--------|-------|
| `capacity_override.py PI-2026-1.1 --list` | Vypise existujici overridy |
| `capacity_override.py PI-2026-1.1 --add --person bob --hours 12` | Prida override |
| `capacity_override.py PI-2026-1.1 --remove --person bob` | Odebere override |

### detect_contributors.py / calibrate_signals.py

| Prikaz | Popis |
|--------|-------|
| `detect_contributors.py` | Prevede `evidence[]` -> `contributors[]` (cw) z realnych signalu |
| `calibrate_signals.py --ground-truth .edpa/data/ground_truth.yaml --heuristics .edpa/config/cw_heuristics.yaml` | Kalibrace signalovych vah (MAD) |

### sync_pr_contributions.py (volitelne, CI)

| Prikaz | Popis |
|--------|-------|
| `sync_pr_contributions.py` | Materializuje PR-thread signaly (`pr_reviewer`, `issue_comment`) do `evidence[]`. Spousti `edpa-contribution-sync.yml` po merge PR; vyzaduje `EDPA_TOKEN`. |

> **Odstraneno v 2.0.0:** `sync.py` (obousmerny sync -- v V2 neexistuje), `issue_types.py` (org Issue Types), `project_setup.py --org/--repo/--project-title` (GitHub Project provisioning -- `project_setup.py` v V2 jen vendoruje engine), `project_views.py` + `create_project_views.py` (Project views / Playwright), `evaluate_cw.py` (nahrazeno `calibrate_signals.py`).

---

## Architektura

V2 je **local-first**: `.edpa/` (backlog v `.md` + config) je jediny zdroj pravdy, git je audit trail. GitHub je volitelny -- jediny tok smerem dovnitr je jednosmerne materializovani PR-thread signalu do `evidence[]`.

```
                  .edpa/  (git) -- JEDINY ZDROJ PRAVDY
        backlog/**/*.md  +  config/  +  iterations/
                                |
              +-----------------+-----------------+
              |                 |                 |
        EDPA engine        backlog.py         board.py
        (vypocet)          (add/tree/wsjf)    (HTML board)
              |                                    |
        +-----+-----+                              v
        |           |                       .edpa/board.html
   reports/     snapshots/                  (lokalni)
   timesheet-*.md  *.json
   xlsx
```

### Tok dat

```
   (volitelne) GitHub PR thread
   reviews / komentare
              |
              |  edpa-contribution-sync.yml (po merge PR)
              |  sync_pr_contributions.py
              v  -- JEDNOSMERNE: signaly -> evidence[]
   +-------------------------------------+
   |  .edpa/  (git) -- ZDROJ PRAVDY      |
   |  backlog *.md  config  iterations   |
   |  evidence[] <- git commit_author    |
   |             <- yaml_edit            |
   |             <- gate transitions     |
   +-------------------------------------+
              |
        detect_contributors.py
        evidence[] -> contributors[] (cw)
              |
        +-----+-----------------------+
        |             |               |
   EDPA engine    reports.py      board.py
   (JS x CW)      timesheety      HTML board
        |
   reports/ + snapshots/ + xlsx
```

> **Odstraneno v 2.0.0:** obousmerny sync GitHub Projects <-> Git, org Issue Types, custom fields. Zadny GitHub Project se neprovisionuje ani nepropaguje.

### Evidence detection

EDPA je evidence-driven. `cw[osoba, item] = contribution_score / Σ_osoby contribution_score`, kde `contribution_score = Σ signal_weight`. Vychozi signalove vahy (`cw_heuristics.yaml`):

| Signal | Vaha | Zdroj |
|--------|------|-------|
| `assignee` | 4.00 | issue assignee |
| `pr_author` | 3.40 | autor PR referujici item |
| `commit_author` | 2.78 | commit s ID (lokalni git, post-commit hook) |
| `pr_reviewer` | 2.25 | odeslany PR review (mimo self) |
| `issue_comment` | 1.14 | komentar na issue/PR (mimo boty) |

Lokalni signaly (`commit_author`, `yaml_edit`, gate transitions) cte engine primo z gitu/YAMLu. PR-thread signaly (`pr_reviewer`, `issue_comment`) prichazeji jen pres volitelny contribution-sync. Manualni `/contribute @person weight:X` (nebo `--contributor`) nese vahu verbatim.

Rolove vahy prispevatelu: owner 1.0 / key 0.6 / reviewer 0.25 / consulted 0.15; `evidence_threshold` 1.0.

### Vypocet EDPA

Od v1.14 jedina vypocetni cesta (zadny simple/full/gates mode). Pro kazdou osobu v iteraci:

1. Sebrat evidenci na kazde polozce -> `contributors[]` s `cw`
2. Pro kazdy par (osoba, polozka): `score = JS x CW`
3. Pro kazdou osobu: `ratio_i = score_i / sum(scores)`
4. Odvozene hodiny: `hours_i = ratio_i x capacity`

Invariant: `sum(DerivedHours) = capacity` (presne, ne priblizne). Feature/Epic/Initiative status transitions navic rozdeluji rodicovsky Job Size pres `gate_weights`.

---

## Troubleshooting

### gh auth (jen volitelny PR-signal sync)

EDPA V2 jadro `gh` nepotrebuje. Pokud selze volitelny contribution-sync workflow na autentizaci, doplnte secret `EDPA_TOKEN` (viz `docs/edpa-token-setup.md`) nebo lokalne:

```bash
gh auth login        # bezny repo scope staci
gh auth status
```

> V2 uz nepotrebuje org scopy (`admin:org`, `project`) -- GitHub Projecty a org Issue Types byly odstraneny v 2.0.0.

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

### Branch naming -- odmitnuty commit/push (git hook)

```
Branch name does not follow EDPA convention.
Required format: {type}/{item-id}-{description}
```

V V2 hlida konvenci lokalni git hook (`--with-hooks`), uz ne CI.

**Reseni:**
- Format: `feature/S-200-omop-parser`, `bugfix/S-215-fix-validation`
- Typ: `feature`, `bugfix`, `hotfix`, `chore`
- Prefix: `S` (Story), `F` (Feature), `E` (Epic), `T` (Task), `D` (Defect), `EV` (Event)
- `main`, `develop`, `release/*` jsou vyjimky (prochazi bez kontroly)

### commit-msg hook -- chybejici reference itemu

```
commit-msg: no item reference found
```

**Reseni:**
- Pridat referenci itemu do zpravy: `feat(S-200): ...`
- Nebo pro commity bez ticketu pouzit prefix `no-ticket:`

### Python -- chybejici zavislosti

```
ERROR: pyyaml required. Install with: pip install pyyaml
```

**Reseni:**

```bash
pip install pyyaml openpyxl ruamel.yaml
```

### Iteration close -- "config not found"

```
ERROR: .edpa/config/people.yaml not found. Run EDPA setup first.
```

**Reseni:**
- Spustit setup (vendoruje engine + naseje configy):

```bash
/edpa:setup
# nebo
python3 .edpa/engine/scripts/project_setup.py
```

- Pripadne zkopirovat ze sablon v `.edpa/engine/templates/*.tmpl`:

```bash
cp .edpa/engine/templates/people.yaml.tmpl .edpa/config/people.yaml
cp .edpa/engine/templates/cw_heuristics.yaml.tmpl .edpa/config/cw_heuristics.yaml
cp .edpa/engine/templates/edpa.yaml.tmpl .edpa/config/edpa.yaml
```

- Soubory v `.edpa/config/*.yaml` (ne `*.yaml.tmpl`) musi byt commitnute v repu

### MAD prilis vysoke (> 0.10)

**Mozne priciny:**
- Strategicke role (BO, PM, Arch) maji systematicky nizsi auto-CW nez realitu
- Git meri jen commity/PR, ne rozhodovani, specifikaci, mentoring

**Reseni:**
1. Analyzovat zaznamy s nejvetsim `abs(auto_cw - confirmed_cw)`
2. Seskupit dle role
3. Upravit `signals:` vahy v `.edpa/config/cw_heuristics.yaml` (zvysit vahu signalu, ktery danou roli reprezentuje)
4. Pripadne pridat manualni `/contribute @person weight:X` u itemu, kde je strategicka prace neviditelna v Gitu
5. Znovu spustit `calibrate_signals.py`

### PR-signal sync -- chybejici evidence z PR

PR-thread signaly (`pr_reviewer`, `issue_comment`) se do `evidence[]` dostanou jen pres volitelny contribution-sync.

**Reseni:**
- Overit, ze je nainstalovan `.github/workflows/edpa-contribution-sync.yml` (`/edpa:setup --with-ci`)
- Overit secret `EDPA_TOKEN` (viz `docs/edpa-token-setup.md`)
- Workflow bezi az **po merge** PR; pred merge jsou v evidenci jen lokalni signaly (`commit_author`, `yaml_edit`)

---

## Slovnicek

| Termin | Vyznam |
|--------|--------|
| **PI** | Planning Interval (AI-native 5 tydnu = 4 delivery + 1 IP; classic SAFe 10 tydnu) |
| **IP** | Innovation & Planning (posledni iterace PI) |
| **JS** | Job Size -- relativni velikost prace (Fibonacci) |
| **BV** | Business Value -- obchodni hodnota |
| **TC** | Time Criticality -- casova kritickost |
| **RR-OE** | Risk Reduction & Opportunity Enablement -- snizeni rizika / odemceni prilezitosti (CLI flag `--rr-oe`, legacy alias `--rr`) |
| **WSJF** | Weighted Shortest Job First = (BV+TC+RR-OE)/JS |
| **CW** | Contribution Weight -- vaha prispevku (0.0 - 1.0); per-item `Σ cw = 1.0` |
| **Signal** | Doklad prispevku z gitu/PR (assignee, pr_author, commit_author, pr_reviewer, issue_comment) s vahou |
| **MAD** | Mean Absolute Deviation -- prumerna absolutni odchylka (metrika kalibrace) |
| **Evidence** | `evidence[]` na itemu -- agregovane signaly; `detect_contributors.py` z nich pocita `contributors[]` |
| **Gate** | Status transition na Feature/Epic/Initiative; rozdeluje rodicovsky JS pres `gate_weights` |
| **Ground truth** | Potvrzena realita od tymu (pro kalibraci) |
