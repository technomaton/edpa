# EDPA — Kompletní E2E test plán

End-to-end ověření celého EDPA workflow od čisté instalace až po uzavření iterace
a vygenerování reportů, včetně oboustranného sync s GitHub Projects.

**Verze plánu:** 1.1 (2026-05-06)
**Pokrývaná verze EDPA:** 1.8.0-beta (engine, sync push/pull, gates default,
sync setup-refresh, idempotent project_setup, contributors `as:` schema, `--check-readiness`,
batch `reports.py`, sub-issue idempotence, schema validation v `validate_syntax.py`)
**Cílový stav po projití:** plugin nainstalovaný, GitHub Project naplněný, jeden uzavřený PI s reporty.

**Co se změnilo proti 1.0:** všechny předchozí E2E nálezy z 2026-05-06 jsou opravené
(viz `docs/E2E-REPORT-2026-05-06.md` pro 18-bodovou matici). Schema backlogu má
**breaking** rename `contributors[].role` → `contributors[].as` a `weight` → `cw`;
legacy YAML migrate jednorázově `python3 .claude/edpa/scripts/migrate_contributors.py`.
Tento test ověřuje, že čistý onboarding (install → setup → engine → reports) projde
**bez ručních zásahů** — engine vrátí non-zero alokaci na první spuštění.

---

## 0. Co tento plán pokrývá

| Fáze | Co se ověřuje                                              | Kritická? |
|------|------------------------------------------------------------|-----------|
| 1    | Instalace pluginu (curl/local), žádná root pollution       | ✅        |
| 2    | `/edpa:setup` — vytvoření GitHub Project, fields, issue_map | ✅        |
| 3    | Backlog (Initiative→Epic→Feature→Story), schémata, hooks    | ✅        |
| 4    | Branche, commity, PR, GitHub Action `branch-check`          | ✅        |
| 5    | `sync push` — vytvoření issues, link parent/child, fields  | ✅        |
| 6    | `sync pull --commit` — typed Status fields, git transitions| ✅        |
| 7    | Konflikty (`sync conflicts`, `sync diff`)                  | ✅        |
| 8    | Recovery (`sync setup-refresh`, ztráta `field_ids`)         | ⚠️        |
| 9    | `/edpa:close-iteration` — engine `--mode gates`             | ✅        |
| 10   | `/edpa:reports` — timesheets, item-costs, XLSX, snapshot    | ✅        |
| 11   | `/edpa:calibrate` readiness (≥ 20 ground-truth)            | ⚠️        |
| 12   | 5-min smoke test (po fresh checkout)                        | ✅        |
| 13   | `kashealth` deployment dry-run                              | ⚠️        |

**Délka plné pasáže fází 1–10:** ~3–4 hodiny manuálně, ~25 minut automatizovanou částí (`pytest`).

---

## 1. Předpoklady (jednorázově)

```bash
# Toolchain
python3 --version          # ≥ 3.10
git --version              # ≥ 2.30
gh --version               # ≥ 2.40
gh auth status             # OK; scope: repo, project, admin:org

# Python knihovny
python3 -m pip install pyyaml openpyxl

# GitHub sandbox repo + org
#   sandbox repo musí být PRÁZDNÝ — push test maže issues
#   org-level Issue Types: Initiative, Epic, Feature, Story
export EDPA_E2E_REPO="technomaton/edpa-e2e-test"
python3 plugin/edpa/scripts/issue_types.py setup --org technomaton
```

**Pass:** všechny příkazy bez chyby, `gh auth status` ukazuje `repo + project + admin:org`.

---

## 2. Test data

Plán používá tři úrovně testovacích vstupů — od nejmenšího po realistický:

| Sada       | Použití                              | Kde leží                           |
|------------|--------------------------------------|------------------------------------|
| **smoke**  | minimální (1×I, 1×E, 1×F, 1×S)       | `tests/test_e2e_install.py` zdroje |
| **sandbox**| 6 itemů, real GH API                 | `tests/test_e2e_sync.py` fixtures  |
| **kashealth-like** | 4 lidé, 8 stories, 2 týdenní PI | připravit ručně dle § 13           |

---

## Fáze 1 — Instalace pluginu

**Cíl:** ověřit, že `install.sh` nainstaluje plugin do `.claude/edpa/`, vytvoří
`.edpa/` strom a NEZAPLNÍ root cílového projektu (žádné `scripts/`, `config/`,
`reports/` v root).

### 1.1 Čistá instalace v `/tmp`

```bash
TARGET=$(mktemp -d -t edpa-test-XXXX)
cd "$TARGET"
git init -q
echo "# Test project" > README.md

# Lokální install (bez GitHub release dependencies)
sh /Users/jurby/projects/edpa/install.sh
```

**Očekávaný výstup:**
- `Python 3.X ✓`, `PyYAML ✓`, `git ✓`, `GitHub CLI ✓`
- `Downloading EDPA plugin...` → `Installation complete`
- `.claude/edpa/scripts/engine.py` existuje
- `.claude/.claude-plugin/plugin.json` existuje

**Pass kritéria:**
```bash
ls "$TARGET" | sort
# Musí obsahovat ≤ {.claude, .edpa, .git, README.md} — žádné jiné položky
[ -f "$TARGET/.claude/edpa/scripts/engine.py" ] && echo "engine OK"
[ -f "$TARGET/.claude/edpa/scripts/sync.py" ] && echo "sync OK"
[ -f "$TARGET/.edpa/config" ] || mkdir -p "$TARGET/.edpa/config"
```

**Fail patterns:**
- root obsahuje `scripts/`, `config/`, `reports/` → **POLLUTION** (porušuje
  `feedback_no_root_pollution.md`)
- `engine.py` chybí → instalace neúplná

### 1.2 Idempotence — opakovaný install

```bash
echo "n" | sh /Users/jurby/projects/edpa/install.sh
# Musí ukázat: "Warning: .claude/edpa/ already exists. Overwrite? [y/N]"
# Při "n": "Aborted."

echo "y" | sh /Users/jurby/projects/edpa/install.sh
# Musí přepsat bez chyby
```

**Pass:** plugin se přepíše, `.edpa/` data zůstanou nedotčena.

### 1.3 Plugin manifest a hooks

```bash
python3 -c "import json; m=json.load(open('$TARGET/.claude/.claude-plugin/plugin.json')); \
  assert m['name']=='edpa'; print('plugin.json OK', m['version'])"

# Validace hooks.json schématu
python3 -c "import json; json.load(open('$TARGET/.claude/hooks/hooks.json'))" \
  && echo "hooks.json valid JSON"
```

**Pass:** validní JSON, `version` odpovídá `CHANGELOG.md`.

### 1.4 Automatizovaný test (pokrytí § 1.1–1.3)

```bash
cd /Users/jurby/projects/edpa
python3 -m pytest tests/test_e2e_install.py -v
```

**Pass:** všechny testy zelené, žádné root entries kromě allow-listu.

---

## Fáze 2 — `/edpa:setup` — inicializace projektu

**Cíl:** vytvořit GitHub Project v2, custom fields, založit issues z lokálního
backlogu, propojit parent/child přes sub-issues a perzistovat IDs do
`.edpa/config/edpa.yaml` + `.edpa/config/issue_map.yaml`.

### 2.1 Příprava configu a backlog templates

```bash
cd "$TARGET"
cp .claude/edpa/templates/project.yaml.tmpl   .edpa/config/edpa.yaml
cp .claude/edpa/templates/people.yaml.tmpl    .edpa/config/people.yaml
cp .claude/edpa/templates/cw_heuristics.yaml.tmpl .edpa/config/heuristics.yaml

# Edituj .edpa/config/edpa.yaml — vyplň sync.github_org, sync.github_repo
$EDITOR .edpa/config/edpa.yaml
```

**Pass:** `edpa.yaml` má vyplněné `sync.github_org`, `sync.github_repo`,
sandbox repo souhlasí s `$EDPA_E2E_REPO`.

### 2.2 Naplnit minimální backlog (smoke set)

```bash
mkdir -p .edpa/backlog/{initiatives,epics,features,stories}
cat > .edpa/backlog/initiatives/I-1.yaml <<EOF
id: I-1
type: Initiative
title: "E2E test initiative"
parent: null
status: Funnel
EOF
cat > .edpa/backlog/epics/E-1.yaml <<EOF
id: E-1
type: Epic
title: "E2E test epic"
parent: I-1
status: Funnel
EOF
cat > .edpa/backlog/features/F-1.yaml <<EOF
id: F-1
type: Feature
title: "E2E test feature"
parent: E-1
status: Funnel
js: 5
EOF
cat > .edpa/backlog/stories/S-1.yaml <<EOF
id: S-1
type: Story
title: "E2E test story"
parent: F-1
status: Backlog
js: 3
iteration: PI-2026-1.1
EOF
```

**Pass:** 4 YAML soubory, `git add .edpa/backlog/ && git commit -m "seed"`.

### 2.3 Dry-run setupu

```bash
python3 .claude/edpa/scripts/project_setup.py \
  --org "$(yq '.sync.github_org' .edpa/config/edpa.yaml)" \
  --repo "$(yq '.sync.github_repo' .edpa/config/edpa.yaml)" \
  --project-title "EDPA-E2E-$(date +%s)" \
  --dry-run
```

**Pass:** výstup obsahuje plán bez API volání:
- `[1] Create project "EDPA-E2E-..."`
- `[2-7] Create N fields, M options`
- `[8] Create 4 issues (I-1, E-1, F-1, S-1)`
- `[9] Persist field_ids → .edpa/config/edpa.yaml`

**Fail:** chybí native Issue Types → spusť
`python3 .claude/edpa/scripts/issue_types.py setup --org <org>` (viz § 1).

### 2.4 Reálný setup

```bash
python3 .claude/edpa/scripts/project_setup.py \
  --org technomaton \
  --repo edpa-e2e-test \
  --project-title "EDPA-E2E-$(date +%s)"
```

**Očekávaný závěr:**
```
══════════════════════════════════════════════════════════════════════
  Setup complete!
  Project: https://github.com/orgs/technomaton/projects/N
  Issues:  4 created
  Fields:  Y values set
  Links:   3 sub-issue links
```

### 2.5 Ověření perzistence

```bash
yq '.sync.github_project_id' .edpa/config/edpa.yaml      # ne-prázdné
yq '.sync.field_ids | keys' .edpa/config/edpa.yaml       # alespoň: Job Size, WSJF, Initiative Status, Epic Status, Feature Status, Story Status
yq '.sync.option_ids | keys' .edpa/config/edpa.yaml      # ne-prázdné
yq 'keys' .edpa/config/issue_map.yaml                    # I-1, E-1, F-1, S-1
```

**Pass kritéria:**
- ✅ `field_ids` obsahuje per-level Status fieldy (Initiative Status, Epic Status, Feature Status, Story Status)
- ✅ `issue_map.yaml` má pro každý item `issue_number`, `project_item_id`, `node_id`
- ✅ V GitHub UI je vidět projekt, 4 issues, parent→child sub-issue linky

**Fail:** prázdné `field_ids` = známý bug v < 1.1.0-beta (`gh project item-edit`
volaný s prázdnými IDs). Pokud nastane → `git pull` čerstvého EDPA, znovu.

### 2.6 Idempotence — druhý setup

```bash
python3 .claude/edpa/scripts/project_setup.py \
  --org technomaton --repo edpa-e2e-test \
  --project-title "EDPA-E2E-...."   # stejný název
```

**Pass:** `Project might already exist — reusing #N`. Žádné duplicitní issues.

---

## Fáze 3 — Backlog hygiena (schémata, hooks)

**Cíl:** ověřit, že úprava YAML přes Edit/Write spustí `validate_on_save.sh`,
že rozbité YAML neprojde a že `validate-item` workflow funguje.

### 3.1 Schema validation — broken YAML

```bash
cd "$TARGET"
echo "id: BAD\nbad indent" > .edpa/backlog/stories/S-broken.yaml
git add .edpa/backlog/stories/S-broken.yaml
git commit -m "test broken yaml"
```

**Pass:** pre-commit hook (instalovaný přes `git config core.hooksPath`)
zablokuje commit s message o invalid YAML.

```bash
# Pokud hooks nejsou aktivované:
sh .claude/edpa/scripts/hooks/install.sh
```

### 3.2 Schema validation — chybějící povinný field

```bash
echo "id: S-2\ntype: Story" > .edpa/backlog/stories/S-2.yaml
# chybí title, parent, js, status, iteration
python3 .claude/edpa/scripts/validate_syntax.py .edpa/backlog/stories/S-2.yaml
```

**Pass:** non-zero exit code, message identifikující chybějící pole.

### 3.3 Hooks — Edit/Write trigger

V Claude Code:
```
Edit .edpa/backlog/stories/S-1.yaml — změň status na "Implementing"
```

**Pass:** v Claude Code transcriptu vidět `Validating syntax...` (statusMessage
z `hooks.json`), žádný error.

**Fail:** validační hook se nespustil → `.claude/hooks/hooks.json` chybí, nebo
`CLAUDE_PLUGIN_ROOT` není nastaven → ověř, že `.claude/edpa/` je symlink/copy
ne ze starší verze.

### 3.4 Branch naming hook (lokálně)

```bash
git checkout -b "wrong-name"
# Pre-commit hook by měl varovat (warning, ne block)
git checkout -b "feature/S-1-test-story"
# OK
```

---

## Fáze 4 — Branche, commity, PR

**Cíl:** ověřit GitHub Action `branch-check.yml`, že odmítá PR s nestandardním
názvem branche, a že commit s referencí na item ID se zaznamená v evidence.

### 4.1 Špatný branch name → PR fail

```bash
cd "$TARGET"
git checkout -b "junk-branch"
echo "// junk" >> README.md
git add . && git commit -m "junk"
git push -u origin junk-branch
gh pr create --title "Junk" --body "test" --base main
```

**Pass:** GitHub Action `branch-check` skončí ❌, PR má failing check.

### 4.2 Správný branch — `feature/S-1-...`

```bash
git checkout main
git checkout -b "feature/S-1-add-readme-section"
echo "## E2E section" >> README.md
git add README.md
git commit -m "feat(S-1): add E2E section"
git push -u origin feature/S-1-add-readme-section
gh pr create --title "feat(S-1): add E2E section" --body "Implements S-1" --base main
```

**Pass:**
- `branch-check` ✅
- `validate-item` workflow zkontroluje, že S-1 existuje v `.edpa/backlog/`
- PR je merge-able

### 4.3 Merge a evidence detection

```bash
gh pr merge --squash --auto
# Po merge:
python3 .claude/edpa/scripts/detect_contributors.py --item S-1 --since 7days
```

**Pass:** výstup obsahuje autora commitu + reviewera (pokud byl), s rolemi
`owner` / `key_contributor` / `reviewer`.

---

## Fáze 5 — `sync push`

**Cíl:** ověřit, že lokální změny (nový item, změněný field) se promítnou do
GitHub Projectu.

### 5.1 Status overview

```bash
python3 .claude/edpa/scripts/sync.py status
```

**Pass:** sekce `GitHub State`, `Local Backlog`, `Issue Map`, všechny řádky
pokud existují.

### 5.2 Diff (dry-run)

```bash
# Přidej nový lokální story (mimo issue_map)
cat > .edpa/backlog/stories/S-2.yaml <<EOF
id: S-2
type: Story
title: "Sync push test story"
parent: F-1
status: Backlog
js: 2
iteration: PI-2026-1.1
EOF

python3 .claude/edpa/scripts/sync.py diff
```

**Pass:** výstup ukáže `+ S-2` (would create) a žádné jiné neočekávané změny.

### 5.3 Skutečný push

```bash
python3 .claude/edpa/scripts/sync.py push
```

**Pass kritéria:**
- ✅ S-2 dostane `issue_number` (záznam v `.edpa/config/issue_map.yaml`)
- ✅ V GitHub UI: nové issue přidané do projektu, parent S-2 ↔ F-1 přes sub-issue
- ✅ Field `Story Status = Backlog`, `Job Size = 2`

### 5.4 Push změny statusu (lokální → GH)

```bash
# Změň S-1 status z Backlog → Implementing
yq -i '.status = "Implementing"' .edpa/backlog/stories/S-1.yaml
git add . && git commit -m "S-1: start implementing"

python3 .claude/edpa/scripts/sync.py push
```

**Pass:** v GitHub Projectu se field `Story Status` změní na "Implementing".
Issue zůstává otevřené.

### 5.5 Push → Done = close issue

```bash
yq -i '.status = "Done"' .edpa/backlog/stories/S-1.yaml
git add . && git commit -m "S-1: done"

python3 .claude/edpa/scripts/sync.py push
```

**Pass:** GitHub issue je `closed`, `Story Status = Done`. Při revertu zpět
na `Implementing` → issue se reopen-ne.

### 5.6 Edge case — push bez setup state

```bash
mv .edpa/config/edpa.yaml .edpa/config/edpa.yaml.bak
python3 .claude/edpa/scripts/sync.py push
```

**Pass:** `Push aborted: GitHub setup state missing or incomplete`.
**Recovery:** `mv .edpa/config/edpa.yaml.bak .edpa/config/edpa.yaml`.

---

## Fáze 6 — `sync pull --commit`

**Cíl:** změny v GitHub UI (status, fields) se promítnou do lokálních YAML
+ commit, který `transitions.py` umí přečíst pro `--mode gates`.

### 6.1 Manuální změna v GitHub UI

V prohlížeči otevři Project → vyber S-2 → změň `Story Status` z `Backlog`
na `Analyzing`. **Nepoužívej CLI** — testujeme reálný UI flow.

### 6.2 Pull bez commitu (preview)

```bash
python3 .claude/edpa/scripts/sync.py pull
```

**Pass:** výstup ukáže `S-2: status Backlog → Analyzing`, lokální YAML se
změní, ale není committed.

### 6.3 Pull s commitem

```bash
git checkout -b "sync/pull-$(date +%s)"
yq -i '.status = "Backlog"' .edpa/backlog/stories/S-2.yaml  # reset
git add . && git commit -m "reset S-2"

python3 .claude/edpa/scripts/sync.py pull --commit
```

**Pass:**
- ✅ `.edpa/backlog/stories/S-2.yaml` má `status: Analyzing`
- ✅ Vznikl commit s message `sync: GitHub Projects -> .edpa/backlog/`
  obsahující change na `S-2`
- ✅ `git log -p --all -- .edpa/backlog/stories/S-2.yaml` ukazuje diff řádku
  `-status: Backlog` / `+status: Analyzing`

### 6.4 Per-level Status fields

```bash
# V GH UI: Initiative I-1 → změnit "Initiative Status" z Funnel na Reviewing
# (typed field, ne default Status!)
python3 .claude/edpa/scripts/sync.py pull
```

**Pass:** lokální `.edpa/backlog/initiatives/I-1.yaml` má `status: Reviewing`.

**Fail:** sync čte default `Status` field místo `Initiative Status` → známý
bug v < 1.1.0-beta. Pokud nastane: zkontroluj `.edpa/config/edpa.yaml`,
že `field_ids` obsahuje `Initiative Status`, `Epic Status`, atd.

### 6.5 Transitions extracted from git

```bash
python3 .claude/edpa/scripts/transitions.py --since 1day --format json
```

**Pass:** JSON obsahuje záznamy pro každý status change z fáze 6.3 a 6.4
s `commit_sha`, `timestamp`, `from_status`, `to_status`, `item_id`.

---

## Fáze 7 — Konflikty

**Cíl:** detekce, kdy se item změnil současně lokálně i na GitHubu.

### 7.1 Vytvoř konflikt

```bash
# Na GitHubu (UI): F-1 → Feature Status = Implementing
# Lokálně:
yq -i '.status = "Reviewing"' .edpa/backlog/features/F-1.yaml
git add . && git commit -m "F-1: reviewing locally"
```

### 7.2 Detekce

```bash
python3 .claude/edpa/scripts/sync.py conflicts
```

**Pass:** výstup obsahuje `F-1: local=Reviewing, remote=Implementing`.

### 7.3 Diff

```bash
python3 .claude/edpa/scripts/sync.py diff
```

**Pass:** označí F-1 jako konfliktní, neaplikuje žádnou změnu.

### 7.4 Manuální resolution (local wins)

```bash
# Předpokládejme, že lokální verze je správná
python3 .claude/edpa/scripts/sync.py push
```

**Pass:** GitHub `Feature Status` = `Reviewing`, `sync conflicts` je čistý.

---

## Fáze 8 — Recovery (`setup-refresh`)

**Cíl:** ověřit, že po ztrátě `field_ids` / `issue_map.yaml` se stav rekonstruuje
z existujícího GitHub Projectu.

### 8.1 Simulace ztráty

```bash
cp .edpa/config/edpa.yaml         /tmp/edpa.yaml.bak
cp .edpa/config/issue_map.yaml    /tmp/issue_map.yaml.bak

# Smaž field_ids a option_ids
yq -i 'del(.sync.field_ids, .sync.option_ids)' .edpa/config/edpa.yaml
rm .edpa/config/issue_map.yaml
```

### 8.2 Refresh

```bash
python3 .claude/edpa/scripts/sync.py setup-refresh
```

**Pass kritéria:**
- ✅ `.edpa/config/edpa.yaml` má znovu `sync.field_ids` (Initiative Status,
  Epic Status, Feature Status, Story Status, Job Size, WSJF, ...)
- ✅ `.edpa/config/issue_map.yaml` má všechny existující GH issues
  (I-1, E-1, F-1, S-1, S-2)
- ✅ Diff vůči `/tmp/*.bak` je prázdný (až na pořadí klíčů)

### 8.3 Push po refresh

```bash
python3 .claude/edpa/scripts/sync.py push
```

**Pass:** žádné nové issues vytvořeny, fields souhlasí.

---

## Fáze 9 — `/edpa:close-iteration`

**Cíl:** spustit engine na uzavřené iteraci, validovat invariants.

### 9.1 Příprava — close all stories in PI-2026-1.1

```bash
# Označ S-1, S-2 jako Done přes sync push
yq -i '.status = "Done"' .edpa/backlog/stories/S-1.yaml
yq -i '.status = "Done"' .edpa/backlog/stories/S-2.yaml
git add . && git commit -m "PI-2026-1.1 close: stories Done"
python3 .claude/edpa/scripts/sync.py push

# Také status transitions na F-1, E-1 (gates evidence)
yq -i '.status = "Done"' .edpa/backlog/features/F-1.yaml
yq -i '.status = "Done"' .edpa/backlog/epics/E-1.yaml
git add . && git commit -m "PI-2026-1.1 close: parents Done"
python3 .claude/edpa/scripts/sync.py push
```

### 9.2 Engine `--mode gates` (default)

```bash
mkdir -p .edpa/reports/iteration-PI-2026-1.1
python3 .claude/edpa/scripts/engine.py \
  --edpa-root .edpa \
  --iteration PI-2026-1.1 \
  --mode gates \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
```

**Pass kritéria:**
- ✅ `edpa_results.json` existuje
- ✅ Sekce `per_person`: pro každou osobu z `people.yaml` má `derived_hours`
- ✅ Sekce `audit_trail`: každý gate transition zaznamenaný se `commit_sha`
- ✅ Žádný warning `transitions.py: no commits` (znamenalo by, že pull --commit
  v § 6.3 nezaznamenal nic)

### 9.3 Engine `--mode simple` srovnání

```bash
python3 .claude/edpa/scripts/engine.py \
  --edpa-root .edpa \
  --iteration PI-2026-1.1 \
  --mode simple \
  --output /tmp/edpa_simple.json
```

**Pass:** `derived_hours` se liší od `gates` (gates kreditují prep work, simple
jen Done). Pokud `simple == gates` → buď není dostatek transitions, nebo všechny
transitions padly v rámci posledního Done.

### 9.4 Invariants

```bash
cd /Users/jurby/projects/edpa
python3 -m pytest tests/test_invariants.py tests/test_gate_allocation.py -v
```

**Pass:** všechny testy zelené, score formule, capacity invariant a ratio sums
platí.

---

## Fáze 10 — `/edpa:reports`

**Cíl:** ze `edpa_results.json` vygenerovat per-person timesheety, item-costs
XLSX, snapshot.

### 10.1 Spuštění reports skill (přes Claude Code)

V Claude Code napsat:
```
/edpa:reports PI-2026-1.1
```

(Nebo manuálně dle `docs/RUNBOOK.md` § 4.)

### 10.2 Ověření výstupů

```bash
ls -la .edpa/reports/iteration-PI-2026-1.1/
# Musí obsahovat:
#   timesheet-<person1>.md  (jeden na osobu z people.yaml s derived_hours > 0)
#   timesheet-<person2>.md
#   ...
#   item-costs.xlsx
#   edpa_results.json (z fáze 9)

ls -la .edpa/snapshots/
# Musí obsahovat: PI-2026-1.1.json
```

**Pass kritéria:**
- ✅ Pro každou osobu: timesheet-<id>.md s breakdown
  (item → role → CW → DerivedHours → Cost)
- ✅ Per-osobu součet `DerivedHours` ≤ `capacity_per_iteration` (z `people.yaml`)
- ✅ Suma všech `DerivedHours` v iteraci ≈ suma všech `cw * effort_units`
  (capacity invariant)
- ✅ Snapshot má `methodology_version`, `engine_mode`, `frozen_at`

### 10.3 Item-costs XLSX

```bash
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('.edpa/reports/iteration-PI-2026-1.1/item-costs.xlsx')
ws = wb.active
for row in ws.iter_rows(values_only=True, max_row=10):
    print(row)
"
```

**Pass:** sloupce `item_id, person, role, cw, derived_hours, hourly_rate, cost`,
součet sloupce `cost` souhlasí s manuálním výpočtem.

### 10.4 PI summary (volitelné)

```bash
# Pokud máš více iterací v PI-2026-1, lze vygenerovat PI-summary
# (skill podporuje --pi)
```

---

## Fáze 11 — Calibration readiness

**Cíl:** ověřit, že `edpa-autocalib` skill správně odmítne běh před prvním PI.

### 11.1 Před prvním PI

```bash
python3 .claude/edpa/scripts/evaluate_cw.py --auto-calibrate
```

**Pass:** skill vypíše warning: `Insufficient ground truth (< 20 records).
Skip until first PI is closed and reviewed.` Žádný `heuristics.yaml` zápis.

### 11.2 Po vytvoření ground truth

(Tento krok dělej až po skutečném PI s manuálním auditem.)

```bash
# Vyplň .edpa/data/ground_truth.yaml — alespoň 20 records s
# {item_id, person, role, manual_cw, auto_cw, source: pi_review}
ls .edpa/data/ground_truth.yaml
```

**Acceptance:** auto-calib loop najde alespoň 5% MAD reduction → `heuristics.yaml`
přepsán s commit message `calibrate: MAD reduction X%`.

---

## Fáze 12 — 5-min smoke test

Po každém zásahu do source repo (změna engine/sync/scripts) běž tento set:

```bash
cd /Users/jurby/projects/edpa

# 1. Unit + integration suite (cca 10s)
python3 -m pytest tests/ -v -m "not e2e"

# 2. Engine smoke
python3 plugin/edpa/scripts/engine.py --status
python3 plugin/edpa/scripts/engine.py --demo

# 3. Sync smoke (proti reálnému GH sandboxu)
python3 plugin/edpa/scripts/sync.py status

# 4. Board smoke
python3 plugin/edpa/scripts/board.py --output /tmp/edpa-board.html
test -s /tmp/edpa-board.html && echo "board OK"

# 5. Hooks (validate_syntax na známém invalid YAML)
echo "id: BAD: bad" | python3 plugin/edpa/scripts/validate_syntax.py /dev/stdin
echo "exit code: $?"   # nenulový
```

**Pass:** všech 5 kroků projde bez chyby.

### 12.1 Plně automatizovaný E2E (volitelné)

```bash
EDPA_E2E_REPO=technomaton/edpa-e2e-test \
  python3 -m pytest tests/test_e2e_sync.py -m e2e -v
```

**Trvání:** 5–6 minut (real GH API). Maže issues a project ve sandboxu —
nikdy neukazovat na repo s reálnými daty!

---

## Fáze 13 — Kashealth deployment dry-run

**Cíl:** připravit a ověřit reálné nasazení do `kashealth.cz` repo, než tam
proteče první commit.

### 13.1 Příprava

```bash
# 1. V kashealth orgu vytvoř Issue Types (Initiative, Epic, Feature, Story)
python3 plugin/edpa/scripts/issue_types.py setup --org kashealth

# 2. Naplň .edpa/config/people.yaml reálným týmem (4–6 lidí, role, FTE,
#    capacity_per_iteration, hourly_rate)
$EDITOR .edpa/config/people.yaml

# 3. Naplň .edpa/config/edpa.yaml: sync.github_org=kashealth, sync.github_repo=…
$EDITOR .edpa/config/edpa.yaml
```

### 13.2 Suchý setup

```bash
python3 .claude/edpa/scripts/project_setup.py \
  --org kashealth --repo <repo> \
  --project-title "Kashealth-PI-2026-1" \
  --dry-run
```

**Pass:** plán je rozumný, žádné API změny.

### 13.3 Reálný setup

Až po explicitní user confirmation:

```bash
python3 .claude/edpa/scripts/project_setup.py \
  --org kashealth --repo <repo> \
  --project-title "Kashealth-PI-2026-1"
```

### 13.4 První PI parallel A/B

První iteraci paralelně počítej `--mode simple` (audit conservative) i `--mode gates`:

```bash
python3 .claude/edpa/scripts/engine.py --iteration PI-2026-1.1 --mode simple \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results_simple.json
python3 .claude/edpa/scripts/engine.py --iteration PI-2026-1.1 --mode gates \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results_gates.json

# Diff per-osobu DerivedHours
python3 -c "
import json
s=json.load(open('.edpa/reports/iteration-PI-2026-1.1/edpa_results_simple.json'))
g=json.load(open('.edpa/reports/iteration-PI-2026-1.1/edpa_results_gates.json'))
for p in s['per_person']:
    sh=s['per_person'][p]['derived_hours']
    gh_=g['per_person'][p]['derived_hours']
    delta=gh_-sh
    print(f'{p:20} simple={sh:6.1f}  gates={gh_:6.1f}  Δ={delta:+6.1f}')
"
```

**Acceptance:**
- ✅ Žádná osoba nemá `gates` < `simple` (gates může jen přidat prep credit)
- ✅ MAD vůči manuálnímu odhadu PM-a ≤ 15 % (1. PI tolerance)
- ✅ Po review: rozhodnutí, jestli přepnout default na `gates`

---

## Akceptační kritéria — celkový plán

Plán je úspěšně provedený, pokud:

| # | Kritérium                                                              | Status |
|---|------------------------------------------------------------------------|--------|
| 1 | `install.sh` proběhne čistě, žádná root pollution                     | ☐      |
| 2 | `project_setup.py` vytvoří GH Project a perzistuje field_ids + issue_map | ☐      |
| 3 | Hooks (`validate_on_save.sh`, pre-commit) blokují broken YAML         | ☐      |
| 4 | `branch-check` workflow odmítne `junk-branch`, akceptuje `feature/S-*`| ☐      |
| 5 | `sync push` vytvoří GH issue z lokálního itemu, nastaví fields, linkne parent | ☐      |
| 6 | `sync pull --commit` přečte typed Status fields (Initiative/Epic/Feature/Story Status) | ☐      |
| 7 | `transitions.py` najde gate transitions ze sync commitů              | ☐      |
| 8 | `sync conflicts` detekuje souběžnou změnu lokál+GH                    | ☐      |
| 9 | `sync setup-refresh` rekonstruuje `field_ids` a `issue_map.yaml`     | ☐      |
| 10| `engine.py --mode gates` projde bez warning a vyrobí audit trail     | ☐      |
| 11| Reports skill vyrobí timesheety + item-costs.xlsx + snapshot          | ☐      |
| 12| `pytest tests/` (118 testů) je 100% zelený                           | ☐      |
| 13| `pytest -m e2e` proti sandboxu projde (5 testů v `test_e2e_sync.py`) | ☐      |
| 14| Kashealth dry-run (§ 13) ukáže rozumný plán bez API zápisu           | ☐      |

---

## Příloha A — Klíčové soubory a co dělají

| Soubor                                          | Role                                  |
|-------------------------------------------------|---------------------------------------|
| `install.sh`                                    | shell installer pluginu               |
| `plugin/edpa/scripts/engine.py`                 | hlavní výpočet derived hours          |
| `plugin/edpa/scripts/sync.py`                   | bidirectional sync GH ↔ .edpa/        |
| `plugin/edpa/scripts/project_setup.py`          | bootstrap GitHub Project              |
| `plugin/edpa/scripts/transitions.py`            | extract status changes z git logu     |
| `plugin/edpa/scripts/validate_syntax.py`        | YAML schema validation                |
| `plugin/edpa/scripts/issue_types.py`            | org-level Issue Type setup            |
| `plugin/edpa/workflows/branch-check.yml`        | GH Action — branch naming             |
| `plugin/edpa/workflows/sync-projects-to-git.yml`| GH Action — periodický pull           |
| `plugin/edpa/workflows/sync-git-to-projects.yml`| GH Action — periodický push           |
| `plugin/edpa/workflows/iteration-close.yml`     | GH Action — automatický close         |
| `plugin/hooks/hooks.json`                       | Claude Code hooks (validate, commit info) |
| `plugin/edpa/scripts/hooks/validate_on_save.sh` | post-Edit/Write validátor             |
| `plugin/edpa/scripts/hooks/edpa_post_commit.sh` | post-Bash commit info                 |
| `plugin/.claude-plugin/plugin.json`             | plugin manifest                       |
| `tests/test_e2e_install.py`                     | automatizace § 1                      |
| `tests/test_e2e_sync.py`                        | automatizace § 5–7 (opt-in `-m e2e`)  |
| `tests/test_invariants.py`                      | automatizace § 9.4                    |
| `tests/test_gate_allocation.py`                 | automatizace § 9.4 pro gates mode     |
| `tests/test_hooks.py`                           | automatizace § 3                      |

---

## Příloha B — Známá omezení a workaround tipy

1. **Gates mode pod-přiděluje bez sync commitů.**
   `transitions.py` čte jen status změny zaznamenané v git logu se zprávou
   rozpoznanou `transitions.py`. Manuální `yq -i .status=...` bez commitu
   nebo s nestandardní commit message nebude započítán. **Workaround:**
   vždy používej `sync pull --commit` nebo manuální commit s message
   `sync: ... -> ...`.

2. **Statický seznam contributorů.** Engine používá jeden contributor list
   per parent item pro VŠECHNY gates. Highly-specialized role (Architekt
   jen u LBC) → over-attribution. **Workaround:** rekalibrace heuristik nebo
   úprava contributor listu v daném itemu.

3. **`field_ids` nelze založit přes UI** — pokud setup.py selhal mezi krokem
   2 a 7, projekt existuje ale fields chybí. **Recovery:**
   - smaž project v GH UI
   - vyčisti `.edpa/config/edpa.yaml` (sekce `sync.field_ids`, `option_ids`)
   - znovu `project_setup.py`

4. **Sandbox repo je destruktivní.** `tests/test_e2e_sync.py` maže issues a
   project v `EDPA_E2E_REPO` mezi runy. Nikdy nepoukazuj na produkční repo!

5. **Schema strictness vs. legacy projects.** Nové itemy musí mít všechny
   povinné fieldy. Migrace ze starší struktury → ručně doplnit. Viz
   `docs/migration-v2.md`.

---

## Příloha C — Rychlé reference příkazy

```bash
# Instalace
curl -fsSL https://edpa.technomaton.com/install.sh | sh

# Setup
python3 .claude/edpa/scripts/project_setup.py --org X --repo Y --project-title "..."

# Sync
python3 .claude/edpa/scripts/sync.py status
python3 .claude/edpa/scripts/sync.py diff
python3 .claude/edpa/scripts/sync.py push
python3 .claude/edpa/scripts/sync.py pull --commit
python3 .claude/edpa/scripts/sync.py conflicts
python3 .claude/edpa/scripts/sync.py setup-refresh

# Engine
python3 .claude/edpa/scripts/engine.py --status
python3 .claude/edpa/scripts/engine.py --demo
python3 .claude/edpa/scripts/engine.py --iteration PI-... --mode gates --output ...

# Board
python3 .claude/edpa/scripts/board.py --open

# Tests
python3 -m pytest tests/                       # offline, 118 testů
EDPA_E2E_REPO=... python3 -m pytest tests/test_e2e_sync.py -m e2e -v   # online
```
