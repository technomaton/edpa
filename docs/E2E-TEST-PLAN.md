# EDPA — Kompletní E2E test plán

End-to-end ověření celého EDPA workflow od čisté instalace až po uzavření iterace
a vygenerování reportů. EDPA V2 je **local-first**: `.edpa/backlog/**/*.md`
(YAML frontmatter) je single source of truth, git je audit trail. GitHub je
**volitelný** — žádný GitHub Project provisioning, žádná oboustranná synchronizace.

**Verze plánu:** 2.1.x (2026-05-31; revize odkazů 2026-06-11, platí pro V2 local-first 2.1+)
**Pokrývaná verze EDPA:** 2.1+ (vendored engine v `.edpa/engine/`, local-first backlog v `.md`,
evidence-driven engine, git hooks pro evidence, volitelný contribution-sync workflow)
**Cílový stav po projití:** plugin nainstalovaný, engine vendorovaný do `.edpa/engine/`,
lokální backlog naplněný, jeden uzavřený PI s reporty + frozen snapshotem.

**Co se změnilo proti V1:** kompletní přechod na local-first architekturu (2.0.0+).
**Odstraněno** (a tedy i z tohoto plánu): GitHub Project provisioning
(`project_setup.py --org/--repo/--project-title`), `issue_types.py`,
`project_views.py`, oboustranný `sync.py` (push/pull/diff/conflicts/setup-refresh),
`issue_map.yaml`, GH sync workflows (`edpa-sync-*.yml`, `edpa-branch-check.yml`,
`edpa-iteration-close.yml`), engine `--mode simple|full`, `evaluate_cw.py`
a `.yaml` backlog soubory. V2 `project_setup.py` pouze **vendoruje engine**
a seeduje `.edpa/`; jediný GH workflow je volitelný `edpa-contribution-sync.yml`.
Tento test ověřuje, že čistý onboarding (install/setup → backlog add → engine →
reports) projde **bez ručních zásahů** a **bez GitHubu** — engine vrátí non-zero
alokaci na první spuštění z lokální evidence.

---

## 0. Co tento plán pokrývá

| Fáze | Co se ověřuje                                                       | Kritická? |
|------|--------------------------------------------------------------------|-----------|
| 1    | Instalace pluginu (curl/local), vendoring `.edpa/engine/`, žádná root pollution | ✅ |
| 2    | `/edpa:setup` / `project_setup.py` — vendoring + seed configů, `id_counters.yaml` | ✅ |
| 3    | Backlog (Initiative→Epic→Feature→Story) přes `backlog.py add`, schémata, hooks | ✅ |
| 4    | Branche, commity, commit-msg/post-commit hooks → `evidence[]`      | ✅        |
| 5    | Iterace (`.edpa/iterations/*.yaml`), `backlog.py status`/`wsjf`    | ✅        |
| 6    | `detect_contributors.py` — normalizace `evidence[]` → `contributors[]` | ✅     |
| 7    | `engine.py` — derived hours, frozen snapshot, XLSX, invariants     | ✅        |
| 8    | `/edpa:reports` — timesheety, item-costs XLSX, snapshot            | ✅        |
| 9    | `/edpa:calibrate` readiness (≥ 20 ground-truth)                    | ⚠️        |
| 10   | (Volitelně) GitHub `--with-ci` contribution-sync workflow         | ⚠️        |
| 11   | 5-min smoke test (po fresh checkout)                               | ✅        |
| 12   | Reálné nasazení dry-run                                            | ⚠️        |

**Délka plné pasáže fází 1–8:** ~1–2 hodiny manuálně, ~10 minut automatizovanou částí (`pytest`).

---

## 1. Předpoklady (jednorázově)

```bash
# Toolchain
python3 --version          # ≥ 3.10
git --version              # ≥ 2.30

# Python knihovny
python3 -m pip install pyyaml openpyxl

# GitHub CLI je VOLITELNÝ — jen pro fázi 10 (contribution-sync workflow).
# Local-first flow (fáze 1–9) běží zcela bez GitHubu.
gh --version               # volitelně, ≥ 2.40
gh auth status             # volitelně; scope: repo (žádný project/admin:org)
```

**Pass:** `python3`, `git` a `pyyaml`/`openpyxl` bez chyby. GitHub není pro
základní pasáž potřeba — žádný org provisioning, žádné Issue Types.

---

## 2. Test data

Plán používá tři úrovně testovacích vstupů — od nejmenšího po realistický:

| Sada       | Použití                              | Kde leží                              |
|------------|--------------------------------------|---------------------------------------|
| **smoke**  | minimální (1×I, 1×E, 1×F, 1×S)       | `tests/test_e2e_install.py` zdroje    |
| **sandbox**| plný local-first cyklus              | `tests/e2e_v2_full/` fixtures         |
| **realistic** | 4 lidé, 8 stories, 2týdenní PI    | připravit ručně dle § 12              |

---

## Fáze 1 — Instalace pluginu

**Cíl:** ověřit, že `install.sh` vendoruje engine do `.edpa/engine/`, založí
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
- `Python 3.X ✓`
- vendoring engine → `.edpa/engine/` → `Installation complete`
- `.edpa/engine/scripts/engine.py` existuje
- `.edpa/engine/scripts/backlog.py` existuje
- `.edpa/engine/VERSION` obsahuje pinnutou verzi (matchuje `plugin.json`)

**Pass kritéria:**
```bash
ls "$TARGET" | sort
# Root smí obsahovat ≤ {.edpa, .git, README.md} — žádné jiné položky
[ -f "$TARGET/.edpa/engine/scripts/engine.py" ]  && echo "engine OK"
[ -f "$TARGET/.edpa/engine/scripts/backlog.py" ] && echo "backlog OK"
[ -s "$TARGET/.edpa/engine/VERSION" ]            && echo "VERSION pinned: $(cat "$TARGET/.edpa/engine/VERSION")"
```

**Fail patterns:**
- root obsahuje `scripts/`, `config/`, `reports/` → **POLLUTION** (porušuje
  `feedback_no_root_pollution.md`)
- engine pod `.claude/edpa/scripts/` místo `.edpa/engine/scripts/` → stará
  V1 cesta, instalace je z předchozí verze
- `engine.py`/`backlog.py` chybí → vendoring neúplný

### 1.2 Idempotence — opakovaný install / re-vendoring

```bash
sh /Users/jurby/projects/edpa/install.sh
# Re-vendoring přepíše .edpa/engine/ bez chyby; .edpa/backlog/ + .edpa/config/
# zůstanou nedotčené (data se nepřepisují, jen engine).
```

**Pass:** engine se přepíše, `.edpa/backlog/` a `.edpa/config/` data zůstanou
nedotčena, `.edpa/engine/VERSION` se aktualizuje.

### 1.3 Engine VERSION pin

```bash
EXPECTED=$(python3 -c "import json; print(json.load(open('/Users/jurby/projects/edpa/plugin/.claude-plugin/plugin.json'))['version'])")
test "$(cat "$TARGET/.edpa/engine/VERSION")" = "$EXPECTED" && echo "VERSION matches plugin.json ($EXPECTED)"
```

**Pass:** `.edpa/engine/VERSION` odpovídá `plugin/.claude-plugin/plugin.json`
(single source of truth verze).

### 1.4 Automatizovaný test (pokrytí § 1.1–1.3)

```bash
cd /Users/jurby/projects/edpa
python3 -m pytest tests/test_e2e_install.py tests/test_project_setup_vendor.py -v
```

**Pass:** všechny testy zelené, žádné root entries kromě allow-listu,
vendoring + VERSION pin OK.

---

## Fáze 2 — `/edpa:setup` — inicializace projektu (local-first)

**Cíl:** vendorovat engine + naseedovat `.edpa/config/{edpa.yaml,people.yaml,
cw_heuristics.yaml,id_counters.yaml}`. **Žádný GitHub Project, žádné
custom fields, žádný `issue_map.yaml`.** `project_setup.py` v V2 bere pouze
`--with-ci/--with-hooks/--with-rules/--root`.

### 2.1 Spuštění setupu

```bash
cd "$TARGET"
python3 .edpa/engine/scripts/project_setup.py --with-hooks --with-rules
# Volitelně přidej --with-ci pro contribution-sync workflow (viz § 10).
```

**Očekávaný závěr:**
```
✓ Vendored engine → .edpa/engine/
✓ Seeded .edpa/config/edpa.yaml
✓ Seeded .edpa/config/people.yaml
✓ Seeded .edpa/config/cw_heuristics.yaml
✓ Seeded .edpa/config/id_counters.yaml
✓ Installed git hooks (--with-hooks)
✓ Copied architectural rules → .claude/rules/ (--with-rules)
```

**Pass kritéria:**
```bash
[ -f .edpa/config/edpa.yaml ]          && echo "edpa.yaml OK"
[ -f .edpa/config/people.yaml ]        && echo "people.yaml OK"
[ -f .edpa/config/cw_heuristics.yaml ] && echo "cw_heuristics.yaml OK"
[ -f .edpa/config/id_counters.yaml ]   && echo "id_counters.yaml OK"
# Git hooks nainstalované (--with-hooks):
[ -f .git/hooks/commit-msg ]  && echo "commit-msg hook OK"
[ -f .git/hooks/post-commit ] && echo "post-commit hook OK"
```

**Fail:** soubory `.edpa/config/*.yaml` chybí → setup neúplný. Pozn.: V2
configy se jmenují `edpa.yaml` (ne `project.yaml`) a `cw_heuristics.yaml`
(ne `heuristics.yaml`).

### 2.2 Editace people.yaml a edpa.yaml

```bash
# Vyplň reálný tým: people[].{id,name,role,team,fte,capacity_per_iteration,email,github}
$EDITOR .edpa/config/people.yaml

# Vyplň project.name (jediné povinné pole, čte engine); funding/organizations volitelně
$EDITOR .edpa/config/edpa.yaml

git add .edpa/config/ && git commit -m "no-ticket: configure team + project"
```

**Pass:** `people.yaml` má alespoň 1–2 osoby s vyplněným `email`
(klíčové — post-commit hook atribuuje evidence jen podle emailů v people.yaml)
a `capacity_per_iteration`. `edpa.yaml` má vyplněný `project.name`.

### 2.3 Ověření id_counters seedu

```bash
python3 -c "import yaml; c=yaml.safe_load(open('.edpa/config/id_counters.yaml')); print(c)"
```

**Pass:** `id_counters.yaml` existuje a obsahuje čítače per typ (Initiative,
Epic, Feature, Story, …) naseedované z existujících file IDs (po čisté
instalaci typicky 0). `backlog.py add` z těchto čítačů alokuje další ID.

---

## Fáze 3 — Backlog (`backlog.py add`, schémata, hooks)

**Cíl:** vytvořit hierarchii Initiative→Epic→Feature→Story přes `backlog.py add`
(lokálně, auto-commit `feat(<ID>): …`, ID z `id_counters.yaml`), ověřit
validaci YAML frontmatteru a parent-hierarchii.

### 3.1 Naplnit minimální backlog (smoke set)

```bash
cd "$TARGET"

# Initiative (bez parenta)
python3 .edpa/engine/scripts/backlog.py add \
  --type Initiative --title "E2E test initiative"

# Epic → Initiative (předpokládáme I-1)
python3 .edpa/engine/scripts/backlog.py add \
  --type Epic --parent I-1 --title "E2E test epic"

# Feature → Epic
python3 .edpa/engine/scripts/backlog.py add \
  --type Feature --parent E-1 --title "E2E test feature" --js 5

# Story → Feature
python3 .edpa/engine/scripts/backlog.py add \
  --type Story --parent F-1 --title "E2E test story" \
  --js 3 --iteration PI-2026-1.1 --status Backlog
```

**Pass kritéria:**
- ✅ Vzniknou `.md` soubory (YAML frontmatter) pod `.edpa/backlog/{initiatives,epics,features,stories}/`
- ✅ ID alokovaná z `id_counters.yaml` (I-1, E-1, F-1, S-1), čítače inkrementované
- ✅ Každé `add` auto-commitne `feat(<ID>): …` (žádný ruční `git add`)
- ✅ Parent hierarchie validovaná (Epic→Initiative, Feature→Epic, Story→Feature);
  pokus o nevalidní parent skončí non-zero exit

```bash
python3 .edpa/engine/scripts/backlog.py tree     # zobrazí hierarchii I-1 → E-1 → F-1 → S-1
git log --oneline -4                              # 4× feat(<ID>): commit
```

### 3.2 Schema validation — broken frontmatter

```bash
printf 'id: BAD\nbad indent\n' > .edpa/backlog/stories/S-broken.md
python3 .edpa/engine/scripts/validate_syntax.py .edpa/backlog/stories/S-broken.md
echo "exit code: $?"   # nenulový
```

**Pass:** non-zero exit code, message o invalid YAML / chybějícím povinném poli.

```bash
# Commit s rozbitým YAML musí pre-commit hook zablokovat (pokud --with-hooks):
git add .edpa/backlog/stories/S-broken.md
git commit -m "feat(S-broken): test"
# → pre-commit zablokuje (invalid YAML); jinak install hooks:
#   sh .edpa/engine/scripts/hooks/install.sh
rm -f .edpa/backlog/stories/S-broken.md
```

### 3.3 Strict schema validation celého backlogu

```bash
python3 .edpa/engine/scripts/validate_syntax.py --strict .edpa/backlog/
python3 .edpa/engine/scripts/backlog.py validate
```

**Pass:** oba projdou (po smazání `S-broken.md`); `backlog validate` ověří
integritu hierarchie (žádní visící parenti, žádné kolize ID).

### 3.4 Hooks — Edit/Write trigger (v Claude Code)

V Claude Code:
```
Edit .edpa/backlog/stories/S-1.md — změň status na "Implementing"
```

**Pass:** v Claude Code transcriptu vidět `Validating syntax...` (statusMessage
z `hooks.json`), žádný error. Pokud se hook nespustí → ověř, že `.claude/hooks/
hooks.json` existuje a `CLAUDE_PLUGIN_ROOT` je nastaven.

---

## Fáze 4 — Branche, commity, git hooks → evidence

**Cíl:** ověřit, že commit-msg hook vyžaduje referenci na item (nebo `no-ticket:`),
a že post-commit hook emituje `evidence[]` (`chore(evidence): …`) pro autory,
jejichž commit email je v `people.yaml`.

### 4.1 Commit bez reference na item → block

```bash
cd "$TARGET"
git checkout -b "feature/S-1-add-readme-section"
echo "// junk" >> README.md
git add README.md
git commit -m "random change"
# → commit-msg hook zablokuje: chybí EDPA item ref a chybí no-ticket: escape
```

**Pass:** commit-msg hook (`check_ticket_attached.py`) skončí non-zero,
zpráva zůstane v bufferu. Rozpoznané escape prefixy: `no-ticket:`,
`[no-ticket]`, `WIP:`, `Merge …`, `chore(evidence):`, `chore(ci-materialization):`.

### 4.2 Správný commit — reference na S-1

```bash
echo "## E2E section" >> README.md
git add README.md
git commit -m "feat(S-1): add E2E section"
```

**Pass:**
- ✅ commit-msg hook propustí (obsahuje `S-1`)
- ✅ post-commit hook (`local_evidence.py`) detekuje `S-1`, emituje
  `commit_author` + `manual:commit_message` signály do `.edpa/backlog/stories/S-1.md`
  → `evidence[]`, a vytvoří follow-up commit `chore(evidence): …`
- ✅ Atribuce proběhne **jen** když commit email ∈ `people.yaml`
  (jinak signál není přiřazen žádné osobě)

```bash
git log --oneline -3                                    # feat(S-1) + chore(evidence)
python3 .edpa/engine/scripts/backlog.py show S-1        # vidět evidence[] blok
```

### 4.3 Evidence při neznámém emailu

```bash
git -c user.email="stranger@nowhere.invalid" commit --allow-empty -m "feat(S-1): foreign commit"
python3 .edpa/engine/scripts/backlog.py show S-1
```

**Pass:** post-commit hook proběhne (fire-and-forget, neblokuje), ale signál
z `stranger@…` se nepřiřadí žádné osobě — evidence atribuovaná pouze pro emaily
přítomné v `people.yaml`. (Gotcha k ověření.)

---

## Fáze 5 — Iterace a backlog status

**Cíl:** založit iteraci v `.edpa/iterations/`, jejíž datové okno pokrývá
commity z fáze 4, a ověřit `backlog.py status`/`wsjf`.

### 5.1 Iterační YAML

```bash
cd "$TARGET"
mkdir -p .edpa/iterations
cat > .edpa/iterations/PI-2026-1.1.yaml <<EOF
id: PI-2026-1.1
start_date: 2026-05-25
end_date: 2026-05-31
EOF
git add .edpa/iterations/ && git commit -m "no-ticket: open iteration PI-2026-1.1"
```

**Pass:** soubor `.edpa/iterations/PI-2026-1.1.yaml` má ISO `start_date`/
`end_date` a okno **pokrývá** timestampy commitů z fáze 4 (engine váží evidenci
podle git timestampů uvnitř okna iterace).

### 5.2 Validace iterací a status

```bash
python3 .edpa/engine/scripts/validate_iterations.py     # start_date ≤ end_date, atd.
python3 .edpa/engine/scripts/backlog.py status          # přehled položek per iterace
python3 .edpa/engine/scripts/backlog.py wsjf            # WSJF ranking backlogu
```

**Pass:** `validate_iterations.py` projde, `status` ukáže S-1 v PI-2026-1.1,
`wsjf` seřadí položky podle WSJF (JS/BV/TC/RR-OE).

### 5.3 Označit položky Done

```bash
# Po dokončení práce nastav status: Done (Edit/Write nebo přímá editace frontmatteru)
# Engine kredituje práci z evidence; status: Done ohraničuje, co spadá do iterace.
$EDITOR .edpa/backlog/stories/S-1.md     # status: Done
git add .edpa/backlog/stories/S-1.md && git commit -m "feat(S-1): mark done"
```

**Pass:** `backlog.py show S-1` ukazuje `status: Done` a neprázdné `evidence[]`.

---

## Fáze 6 — `detect_contributors.py` — normalizace evidence → contributors

**Cíl:** ověřit, že `detect_contributors.py` přečte `evidence[]` a zapíše
normalizovaný `contributors[]` (per-item CW mapa), který čte engine.
**Toto je povinný krok před enginem** — engine čte `contributors[]`,
ne `evidence[]`; bez normalizace vrátí 0 h.

### 6.1 Refresh contributors[] pro všechny položky

```bash
cd "$TARGET"
python3 .edpa/engine/scripts/detect_contributors.py --all-items
```

**Pass kritéria:**
- ✅ Pro každou položku s `evidence[]` se zapíše `contributors[]` se `cw`
  (Σ napříč osobami = 1.0) + `contribution_score` (raw sum signal weights)
- ✅ Položky bez `evidence[]` jsou no-op (idempotentní)
- ✅ Auto-commit `chore(contributors): …`
- ✅ Role-váhy: owner 1.0 / key 0.6 / reviewer 0.25 / consulted 0.15,
  evidence_threshold 1.0

```bash
python3 .edpa/engine/scripts/backlog.py show S-1     # vidět contributors[] s cw
```

**Fail:** prázdný `contributors[]` po běhu → buď žádná evidence v okně,
nebo commit emaily nejsou v `people.yaml` (viz § 4.3).

---

## Fáze 7 — `engine.py` — výpočet, snapshot, invariants

**Cíl:** spustit engine na iteraci PI-2026-1.1, vyrobit `edpa_results.json`,
frozen snapshot a XLSX, validovat invariants (Σ hours == capacity per osoba).
Engine je **evidence-driven** a má **jednu výpočtovou cestu** (žádný `--mode`).

### 7.1 Spuštění engine

```bash
mkdir -p .edpa/reports/iteration-PI-2026-1.1
# Engine rozliší .edpa/ chůzí nahoru z CWD (nebo přes EDPA_ROOT / --edpa-root) —
# spouštěj z rootu projektu.
python3 .edpa/engine/scripts/engine.py \
  --edpa-root .edpa \
  --iteration PI-2026-1.1 \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
```

**Pass kritéria:**
- ✅ `edpa_results.json` existuje; top-level `people[]`, každá osoba má
  `total_derived`, `items[]`, `invariant_ok`, `capacity`
- ✅ Frozen snapshot `.edpa/snapshots/PI-2026-1.1.json` (klíče
  `snapshot_version`, `methodology`, `capacity_registry`, `derived_reports`,
  `items[]`, `invariants.all_passed`, `frozen_at`)
- ✅ `edpa-results.xlsx` v report adresáři (taby `Team Summary` + `Item Costs`)
- ✅ Žádný `WARN: … Σ contributors[].cw …` (signalizoval by nenormalizovaný
  contributors blok — viz fáze 6)
- ✅ Per osobu z `people.yaml` s evidencí: `total_derived` > 0

### 7.2 Invariants

```bash
cd /Users/jurby/projects/edpa
python3 -m pytest tests/test_invariants.py tests/test_gate_allocation.py -v
```

**Pass:** všechny testy zelené — score formule, capacity invariant
(Σ DerivedHours per osoba == její `capacity_per_iteration`) a ratio sums platí.

```bash
# Ad-hoc kontrola na reálném výstupu:
python3 -c "
import json
r=json.load(open('$TARGET/.edpa/reports/iteration-PI-2026-1.1/edpa_results.json'))
assert r['all_invariants_passed'], 'invariants failed'
for p in r['people']:
    print(f\"{p['id']:18} derived={p['total_derived']:6.1f}  cap={p['capacity']:5}  ok={p['invariant_ok']}\")
"
```

### 7.3 Idempotence snapshotu

```bash
# Druhý běh nad identickými vstupy nesmí vyrobit nový _revN snapshot
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.1 \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
ls .edpa/snapshots/
```

**Pass:** stále jen `PI-2026-1.1.json` (případně refresh `frozen_at`), žádný
`PI-2026-1.1_rev1.json` — payload hash je stabilní mimo timestampy.

---

## Fáze 8 — `/edpa:reports`

**Cíl:** ze `edpa_results.json` vygenerovat per-person timesheety + team rollup.

### 8.1 Spuštění reports (přes Claude Code nebo CLI)

V Claude Code:
```
/edpa:reports PI-2026-1.1
```

Nebo manuálně:
```bash
cd "$TARGET"
python3 .edpa/engine/scripts/reports.py PI-2026-1.1 --edpa-root .edpa
```

### 8.2 Ověření výstupů

```bash
ls -la .edpa/reports/iteration-PI-2026-1.1/
# Musí obsahovat:
#   timesheet-<person_id>.md   (jeden na osobu s derived > 0)
#   timesheet-team.md          (agregovaný team rollup)
#   edpa-results.xlsx          (Team Summary + Item Costs, z fáze 7)
#   edpa_results.json          (z fáze 7)

ls -la .edpa/snapshots/         # PI-2026-1.1.json (frozen)
```

**Pass kritéria:**
- ✅ Pro každou osobu s derived > 0: `timesheet-<id>.md` s breakdown
  (item → CW → Score → Ratio → DerivedHours; role odvozená v display time)
- ✅ Per-osobu řádek `Total: Xh / Yh capacity` (Σ DerivedHours ≤ `capacity`)
- ✅ `timesheet-team.md` agreguje všechny osoby
- ✅ Snapshot má `snapshot_version`, `methodology`, `frozen_at`

### 8.3 edpa-results XLSX (two tabs)

```bash
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('$TARGET/.edpa/reports/iteration-PI-2026-1.1/edpa-results.xlsx')
assert wb.sheetnames == ['Team Summary', 'Item Costs'], wb.sheetnames
ws = wb['Item Costs']
for row in ws.iter_rows(values_only=True, max_row=10):
    print(row)
"
```

**Pass:** taby `Team Summary` + `Item Costs`, sloupce `Item, Level, JS, Person,
CW, Score, Ratio, Hours`; součet `Hours` per osobu odpovídá `capacity`
z people.yaml + případnému iteration override. Sazby/cost EDPA dnes neprodukuje —
náklady aplikuje separátní (privátní) cost registry mimo repo.

### 8.4 PI summary (volitelné)

```bash
# Pokud máš více iterací v PI-2026-1, agreguj přes --pi:
python3 .edpa/engine/scripts/reports.py --pi PI-2026-1 --edpa-root .edpa
# → pi-summary-PI-2026-1.md
```

---

## Fáze 9 — Calibration readiness

**Cíl:** ověřit, že `/edpa:autocalib` / `/edpa:calibrate` správně odmítne běh
před prvním PI s dostatkem ground truth.

### 9.1 Před prvním PI

```bash
python3 .edpa/engine/scripts/calibrate_signals.py --auto-calibrate
```

**Pass:** vypíše warning typu `Insufficient ground truth (< 20 records).
Skip until first PI is closed and reviewed.` Žádný zápis do
`cw_heuristics.yaml`.

### 9.2 Po vytvoření ground truth

(Tento krok dělej až po skutečném PI s manuálním auditem.)

```bash
# Vyplň ground-truth korpus — alespoň 20 records s
# {item_id, person, role, manual_cw, auto_cw, source: pi_review}
python3 .edpa/engine/scripts/calibrate_signals.py --auto-calibrate
```

**Acceptance:** auto-calib loop (Monte Carlo + coordinate descent na MAD)
najde alespoň 5 % MAD reduction → `cw_heuristics.yaml` přepsán s commit message
`calibrate: MAD reduction X%`.

---

## Fáze 10 — (Volitelně) GitHub contribution-sync workflow

**Cíl:** ověřit, že volitelný `--with-ci` workflow materializuje PR-thread
evidenci (review/comment), která **neexistuje v git historii**. Local-first
flow (fáze 1–9) ji nepotřebuje — primární atribuce běží přes post-commit hook.

### 10.1 Instalace workflow

```bash
cd "$TARGET"
python3 .edpa/engine/scripts/project_setup.py --with-ci
# → zkopíruje .github/workflows/edpa-contribution-sync.yml
[ -f .github/workflows/edpa-contribution-sync.yml ] && echo "CI workflow OK"
```

**Pass:** existuje **jen** `edpa-contribution-sync.yml` (jediný V2 GH workflow).
Žádné `edpa-sync-*.yml`, `edpa-branch-check.yml` ani `edpa-iteration-close.yml`.

### 10.2 Sekret a trigger

```bash
# Workflow běží v default merge-only módu: trigger pull_request: closed (merged==true).
# Pro cross-repo / PAT materializaci nastav sekret EDPA_TOKEN v repo settings
# (jinak používá GITHUB_TOKEN). Po merge PR spustí sync_pr_contributions.py,
# který zapíše pr_reviewer + issue_comment signály do evidence[].
gh secret set EDPA_TOKEN     # volitelně, jen pokud GITHUB_TOKEN nestačí
```

**Pass:** po merge PR (který referuje item) workflow proběhne a vytvoří commit
`chore(ci-materialization): …` s PR-thread evidencí. Při uzavírání iterace
lze **otevřené** PR doplnit lokálně:
```bash
python3 .edpa/engine/scripts/sync_pr_contributions.py --pr <N> --rebuild --skip-commit
```

### 10.3 Automatizovaný CI-materialization test

```bash
cd /Users/jurby/projects/edpa
python3 -m pytest tests/test_e2e_v2_ci_materialization.py -v
```

**Pass:** testy materializace PR-thread evidence zelené.

---

## Fáze 11 — 5-min smoke test

Po každém zásahu do source repo (změna engine/scripts) běž tento set:

```bash
cd /Users/jurby/projects/edpa

# 1. Unit + integration suite (cca 10s, offline, local-first)
python3 -m pytest tests/ -v -m "not e2e"

# 2. Engine smoke
python3 plugin/edpa/scripts/engine.py --status
python3 plugin/edpa/scripts/engine.py --demo

# 3. Backlog smoke
python3 plugin/edpa/scripts/backlog.py --help

# 4. Board smoke
python3 plugin/edpa/scripts/board.py --output /tmp/edpa-board.html
test -s /tmp/edpa-board.html && echo "board OK"

# 5. Hooks (validate_syntax na známém invalid YAML)
printf 'id: BAD: bad\n' | python3 plugin/edpa/scripts/validate_syntax.py - --kind yaml
echo "exit code: $?"   # nenulový
```

**Pass:** všech 5 kroků projde bez chyby (krok 5 vrátí nenulový exit u invalid YAML).

### 11.1 Plně automatizovaný E2E (volitelné)

```bash
cd /Users/jurby/projects/edpa
python3 -m pytest tests/test_e2e_v2_ci_materialization.py -m e2e -v
# Plus end-to-end fixtures v tests/e2e_v2_full/ (lokální cyklus, bez GH).
```

**Trvání:** ~1–2 minuty. Local-first E2E nepotřebuje žádný sandbox repo
ani destruktivní GH operace.

---

## Fáze 12 — Reálné nasazení dry-run

**Cíl:** připravit a ověřit reálné nasazení do produkčního repo, než tam
proteče první commit.

### 12.1 Příprava

```bash
cd <project-repo>

# 1. Vendoring engine + seed configů + hooks
python3 /path/to/.edpa/engine/scripts/project_setup.py --with-hooks --with-rules
# (nebo: curl -fsSL https://edpa.technomaton.com/install.sh | sh)

# 2. Naplň .edpa/config/people.yaml reálným týmem (4–6 lidí, role, FTE,
#    capacity_per_iteration, email, github). Sazby (hourly_rate) NEDÁVAT —
#    drží privátní cost registry mimo repo. EMAIL je klíčový pro atribuci.
$EDITOR .edpa/config/people.yaml

# 3. Naplň .edpa/config/edpa.yaml: project.name (+ funding/organizations volitelně)
$EDITOR .edpa/config/edpa.yaml
```

### 12.2 Validace před prvním commitem

```bash
python3 .edpa/engine/scripts/validate_syntax.py --strict .edpa/backlog/
python3 .edpa/engine/scripts/backlog.py validate
python3 .edpa/engine/scripts/validate_iterations.py
python3 .edpa/engine/scripts/engine.py --status
```

**Pass:** vše projde, engine vidí `.edpa/` (chůze nahoru z CWD), žádné chyby
schématu.

### 12.3 První PI dry-run

Až po explicitní user confirmation, založ první iteraci, naplň backlog přes
`backlog.py add`, odpracuj na branchích s commity referujícími položky, pak:

```bash
# Stage 1 (volitelně): capacity overrides (PTO/sick/overtime)
python3 .edpa/engine/scripts/capacity_override.py PI-2026-1.1 --list

# Stage 2b: POVINNÉ — normalizace evidence → contributors
python3 .edpa/engine/scripts/detect_contributors.py --all-items

# Stage 2c: engine + reports
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.1 \
  --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json
python3 .edpa/engine/scripts/reports.py PI-2026-1.1 --edpa-root .edpa
```

**Acceptance:**
- ✅ Engine vrátí non-zero derived hours pro osoby s evidencí
- ✅ Σ DerivedHours per osoba == `capacity_per_iteration` (invariant_ok)
- ✅ Frozen snapshot v `.edpa/snapshots/`
- ✅ MAD vůči manuálnímu odhadu PM-a ≤ 15 % (1. PI tolerance) → vstup pro
  `/edpa:calibrate` po review

---

## Akceptační kritéria — celkový plán

Plán je úspěšně provedený, pokud:

| # | Kritérium                                                                  | Status |
|---|----------------------------------------------------------------------------|--------|
| 1 | `install.sh` proběhne čistě, vendoruje `.edpa/engine/`, žádná root pollution | ☐    |
| 2 | `project_setup.py` naseeduje `.edpa/config/*` + `id_counters.yaml` (žádný GH Project) | ☐ |
| 3 | `backlog.py add` založí I/E/F/S `.md`, alokuje ID, auto-commitne `feat(<ID>):` | ☐ |
| 4 | Schema validation (`validate_syntax.py`, `backlog validate`) blokuje broken YAML | ☐ |
| 5 | commit-msg hook vyžaduje item ref / `no-ticket:`; post-commit emituje `evidence[]` | ☐ |
| 6 | Evidence atribuovaná jen pro emaily ∈ `people.yaml`                        | ☐      |
| 7 | `detect_contributors.py --all-items` normalizuje `evidence[]` → `contributors[]` | ☐ |
| 8 | `engine.py` vyrobí `edpa_results.json` + frozen snapshot + XLSX bez warningu | ☐    |
| 9 | Invariants: Σ DerivedHours per osoba == capacity (`invariant_ok`)          | ☐      |
| 10| Reports skill vyrobí timesheety + `timesheet-team.md`                      | ☐      |
| 11| `pytest tests/ -m "not e2e"` (~565 testů) je 100% zelený                   | ☐      |
| 12| (Volitelně) `--with-ci` nainstaluje **jen** `edpa-contribution-sync.yml`   | ☐      |
| 13| Reálné nasazení dry-run (§ 12) ukáže rozumný výpočet bez ručních zásahů    | ☐      |

---

## Příloha A — Klíčové soubory a co dělají

| Soubor                                              | Role                                       |
|-----------------------------------------------------|--------------------------------------------|
| `install.sh`                                        | shell installer — vendoruje engine do `.edpa/engine/` |
| `.edpa/engine/scripts/engine.py`                    | hlavní výpočet derived hours + snapshot + XLSX |
| `.edpa/engine/scripts/backlog.py`                   | git-native backlog CLI (`add`/`tree`/`status`/`wsjf`/`validate`) |
| `.edpa/engine/scripts/project_setup.py`             | V2 bootstrap — vendoring + seed configů (local-only) |
| `.edpa/engine/scripts/detect_contributors.py`       | normalizace `evidence[]` → `contributors[]` |
| `.edpa/engine/scripts/local_evidence.py`            | post-commit emitter (`commit_author` signály) |
| `.edpa/engine/scripts/sync_pr_contributions.py`     | (volitelně) materializace PR-thread evidence |
| `.edpa/engine/scripts/reports.py`                   | per-person timesheety + team/PI summary    |
| `.edpa/engine/scripts/board.py`                     | HTML Kanban snapshot                       |
| `.edpa/engine/scripts/validate_syntax.py`           | YAML frontmatter schema validation         |
| `.edpa/engine/scripts/calibrate_signals.py`         | auto-kalibrace CW vah (Monte Carlo + coord descent) |
| `.edpa/engine/scripts/hooks/commit-msg-ticket-attached` | commit-msg hook — vyžaduje item ref / escape |
| `.edpa/engine/scripts/hooks/post-commit-evidence`   | post-commit hook — emituje evidence        |
| `.edpa/engine/scripts/hooks/pre-commit-id-safety`   | pre-commit hook — ID safety                |
| `plugin/edpa/templates/github-workflows/edpa-contribution-sync.yml` | (volitelně) jediný V2 GH Action |
| `plugin/hooks/hooks.json`                           | Claude Code hooks (validate, commit info)  |
| `plugin/.claude-plugin/plugin.json`                 | plugin manifest (single source of truth verze) |
| `tests/test_e2e_install.py`                         | automatizace § 1                           |
| `tests/test_project_setup_vendor.py`                | automatizace vendoring (§ 1–2)             |
| `tests/test_backlog_add.py`                         | automatizace § 3                           |
| `tests/test_local_evidence.py`                      | automatizace § 4 (evidence hook)           |
| `tests/test_invariants.py`                          | automatizace § 7.2                         |
| `tests/test_gate_allocation.py`                     | automatizace § 7.2 (alokace)               |
| `tests/test_e2e_v2_ci_materialization.py`           | automatizace § 10 (opt-in `-m e2e`)        |
| `tests/e2e_v2_full/`                                | end-to-end local-first fixtures            |

---

## Příloha B — Známá omezení a workaround tipy

1. **Engine čte `contributors[]`, ne `evidence[]`.** Pokud vynecháš Stage 2b
   (`detect_contributors.py --all-items`), engine vidí prázdné `contributors[]`
   a vrátí **0 h derived** pro každou položku, která přišla přes PR/commit —
   bez chyby, jen tichá nula. **Workaround:** vždy spusť
   `detect_contributors.py --all-items` před enginem.

2. **Evidence jen pro emaily v `people.yaml`.** Post-commit hook atribuuje
   `commit_author` jen když commit email ∈ `people.yaml[].email`. Cizí emaily
   se nezapočítají. **Workaround:** udržuj `email:` u každé osoby aktuální;
   pro multi-contract lidi viz multi-role sekce v `people.yaml`.

3. **Datové okno iterace musí pokrýt commity.** Engine váží evidenci podle git
   timestampů uvnitř `start_date`/`end_date` iterace. Commity mimo okno se
   nezapočítají. **Workaround:** ověř `validate_iterations.py` a okno před enginem.

4. **Engine resolvuje `.edpa/` chůzí nahoru z CWD** (nebo přes `EDPA_ROOT` /
   `--edpa-root`). Spouštěj z rootu projektu, jinak `.edpa/ not found`.

5. **Otevřené PR při close.** `edpa-contribution-sync.yml` v default módu
   commitne až na `pull_request: closed`. Otevřené PR doplň před enginem:
   `sync_pr_contributions.py --pr <N> --rebuild --skip-commit`.

6. **Schema strictness.** Nové položky musí mít validní YAML frontmatter
   (povinné fieldy). Legacy V1 `.yaml` backlog migruj jednorázově
   `migrate_backlog_yaml_to_md.py`; V1→V2 celkově `migrate_v1_to_v2.py`.

---

## Příloha C — Rychlé reference příkazy

```bash
# Instalace (vendoruje engine do .edpa/engine/)
curl -fsSL https://edpa.technomaton.com/install.sh | sh

# Setup (local-only: vendoring + seed configů; --with-ci/--with-hooks/--with-rules)
python3 .edpa/engine/scripts/project_setup.py --with-hooks --with-rules

# Backlog (local-first, auto-commit feat(<ID>):)
python3 .edpa/engine/scripts/backlog.py add --type Story --parent F-1 --title "..." --js 3 --iteration PI-2026-1.1
python3 .edpa/engine/scripts/backlog.py tree
python3 .edpa/engine/scripts/backlog.py status
python3 .edpa/engine/scripts/backlog.py wsjf
python3 .edpa/engine/scripts/backlog.py validate

# Evidence → contributors (POVINNÉ před enginem)
python3 .edpa/engine/scripts/detect_contributors.py --all-items

# Engine (jedna výpočtová cesta; píše JSON + snapshot + XLSX)
python3 .edpa/engine/scripts/engine.py --status
python3 .edpa/engine/scripts/engine.py --demo
python3 .edpa/engine/scripts/engine.py --edpa-root .edpa --iteration PI-2026-1.1 --output .edpa/reports/iteration-PI-2026-1.1/edpa_results.json

# Reports
python3 .edpa/engine/scripts/reports.py PI-2026-1.1 --edpa-root .edpa
python3 .edpa/engine/scripts/reports.py --pi PI-2026-1 --edpa-root .edpa

# Board
python3 .edpa/engine/scripts/board.py --open

# Calibrate
python3 .edpa/engine/scripts/calibrate_signals.py --auto-calibrate

# Tests
python3 -m pytest tests/ -m "not e2e"                                  # offline, ~565 testů
python3 -m pytest tests/test_e2e_v2_ci_materialization.py -m e2e -v    # opt-in CI materialization
```
