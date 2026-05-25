# EDPA V2 — Architecture Verification

> **Status:** Verifikace návrhu V2, založeno na simulaci a inventáři současného kódu.
> **Související:** [concept.md](./concept.md), [plan.md](./plan.md), [decisions.md](./decisions.md)

Cíl tohoto dokumentu: nezávisle ověřit, zda V2 architektura **reálně funguje end-to-end**, jaké signály engine zachová, a kde leží konkrétní riziko degradace. Není to design — je to **stress test designu**.

## 1. Metodika

1. **Inventář současných signálů** — co engine pulluje a odkud (přímý audit kódu `engine.py`, `detect_contributors.py`, `cw_heuristics.yaml.tmpl`)
2. **Mapování zdrojů do V2** — pro každý signál: zachovaný / optional přes `gh` / ztracený
3. **Tool/skill compatibility matrix** — kompletní výčet MCP tools, skills a scriptů s V2 statusem
4. **Konkrétní simulace** — reálná closed Story (S-200) projektována přes V2 pipeline ve dvou scénářích (s `gh` / bez `gh`)
5. **Identifikace rizik** — kde V2 degraduje a o kolik
6. **Findings** — konkrétní mezery v plánu, které je třeba doplnit
7. **Confidence assessment** — go/no-go per oblast

## 2. Signal landscape (současný stav)

EDPA CW (Code Work) computation má **dvě fáze**:
1. **Pre-compute** — `detect_contributors.py` pulluje signály z GH+git a píše `contributors[]` blok do YAML
2. **Consume** — `engine.py` čte hotové `cw` hodnoty z YAML, dělá kapacitní výpočet — **nikdy nevolá `gh` přímo**

Kritický důsledek: **engine sám je už dnes V2-clean**. Otázka degradace V2 leží výhradně ve fázi 1 (`detect_contributors.py`).

### 2.1 Signal weights (z `plugin/edpa/templates/cw_heuristics.yaml.tmpl`)

| Signál | Weight | Zdroj | Bez `gh` |
|---|---:|---|---|
| `assignee` | **4.0** | GH issue assignee | ❌ ztráta |
| `pr_author` | **3.4** | GH PR meta | ❌ ztráta |
| `commit_author` | **2.78** | GH PR commits → ale **lze z `git log`** | ✅ zachováno (přes git) |
| `pr_reviewer` | **2.25** | GH PR reviews | ❌ ztráta |
| `issue_comment` | **1.14** | GH issue/PR comments | ❌ ztráta |
| `manual:commit_message` | dle directive | `/contribute @X weight:Y` v commit msg | ✅ zachováno (git) |
| `manual:pr_body` | dle directive | `/contribute` v PR body | ⚠️ částečně (jen pokud `gh`) |
| `manual:issue_body` | dle directive | `/contribute` v issue body | ❌ ztráta |
| `yaml_edit:*` | 0.5–5.0 | git diff backlog YAML | ✅ zachováno (git) |
| **gate_events** | 0.05–0.50 | git log + transitions.py | ✅ zachováno (git) |
| **flow metrics** (`edpa_flow_metrics`) | n/a | YAML frontmatter timestamps | ✅ zachováno (V2 plní z `_git_timestamps.py`) |

**Součet vah primárních signálů (sums):**
- Total: 13.57
- GH-only: assignee + pr_author + pr_reviewer + issue_comment = **10.79 (79.5 %)**
- Git-native: commit_author = **2.78 (20.5 %)**

**Toto je největší finding verifikace:** bez `gh` ztrácíme **~80 % vážených signal typů**, pokud bychom se spoléhali jen na auto-detection. Mitigace: yaml_edit signály + gate events + manual `/contribute` v commit msgs **kompenzují** podstatnou část (viz simulace S-200 níže).

## 3. V2 evidence pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                     DETECT_CONTRIBUTORS.PY (V2 refactored)           │
│                                                                      │
│   ┌─────────────────────────┐         ┌──────────────────────────┐   │
│   │ gh_authenticated() ?    │── Yes ─►│ Full evidence pipeline    │   │
│   │   AND                   │         │ - gh issue view assignees │   │
│   │ edpa.yaml:              │         │ - gh pr view author/...   │   │
│   │   evidence.use_gh=true  │         │ - gh issue view comments  │   │
│   └────────────┬────────────┘         │ + git log + yaml_edit     │   │
│                │                       │ + gate_events             │   │
│                │ No                    └──────────────────────────┘   │
│                ▼                                                      │
│   ┌──────────────────────────────────────────────────────────────┐    │
│   │ Fallback: git-only pipeline                                  │    │
│   │ - git log --pretty (commit_author, manual:commit_message)    │    │
│   │ - yaml_edit signals (structural diffs)                       │    │
│   │ - gate_events (status transition log)                        │    │
│   │ + warning to stderr: "Reduced signal — gh not available"     │    │
│   └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
            Σ contribution_scores → normalize per item → cw
                                  │
                                  ▼
          .edpa/backlog/{type}/{ID}.md contributors[] block
                                  │
                                  ▼
    ENGINE (engine.py) — čte cw z YAML, dělá kapacity allocation
              ↓ (this part is unchanged, fully local already)
    edpa_results.json → reports → snapshots
```

## 4. Simulace: S-200 trace

**Položka:** `.edpa/backlog/stories/S-200.md` (OMOP parser impl., status=Done)

**Současný stav (kopírováno z YAML):**
```yaml
contributors:
- person: turyna   # owner
  cw: 1.0
- person: tuma     # key
  cw: 0.6
- person: urbanek  # reviewer
  cw: 0.3
```

**Hypotetické signal sources** (rekonstruováno dle rolí):
- **turyna** (owner): assignee + pr_author + commit_author + yaml_edit:create
- **tuma** (key): commit_author + možná pr_reviewer
- **urbanek** (reviewer): pr_reviewer + issue_comment

### 4.1 V2 **s** optional `gh` (default, ADR-011)

Pipeline beží identicky jako dnes. `gh_authenticated() = true` → full evidence pull. Výsledek: **identický s aktuálním stavem**. Žádná ztráta signálu.

```yaml
# detect_contributors.py output (V2 with gh):
contributors:
- person: turyna   ; cw: 1.0     # full signal: assignee + pr_author + commit_author + yaml_edit:create
- person: tuma     ; cw: 0.6     # commit_author + maybe pr_reviewer
- person: urbanek  ; cw: 0.3     # pr_reviewer + issue_comment
```

✅ **Zero regression.**

### 4.2 V2 **bez** `gh` (offline / no auth)

`gh_authenticated() = false` → fallback to git-only. Available signály:

| Osoba | Git-native signály | Score |
|---|---|---:|
| **turyna** | `commit_author` (2.78) + `yaml_edit:create` (5.0) + `yaml_edit:scalar_change` na status flip (0.5) | **8.28** |
| **tuma** | `commit_author` (2.78) — pokud commitoval | **2.78** |
| **urbanek** | (nic git-native, pokud jen reviewoval bez commitu) | **0.00** |

Po normalizaci: turyna cw=0.75, tuma cw=0.25, **urbanek cw=0** ← **kritická ztráta**.

**Co je špatně:**
- Urbanek měl reálný contribution (review), ale V2 ho bez `gh` nevidí
- Engine ho nebude credit-ovat v capacity allocation
- Reports budou ukazovat "urbanek did nothing on S-200" — což je nepravdivé

**Mitigace (v rámci V2 designu):**
1. **Convention: `/contribute` v commit msgs** — reviewer otevírá PR, ale prosí autora, ať do merge commit msg napíše `/contribute @urbanek weight:0.3 as:reviewer`. Vyžaduje disciplínu týmu.
2. **`gh` jako default** — ADR-011 už říká `use_gh: true` defaultně. Bez `gh auth` engine sám hláskuje warning, ale počítá. Pokud team `gh` opustí, vědomě akceptuje degradaci.
3. **Autocalib s "no-gh" profilem** — Monte Carlo by mohl optimalizovat **dva sets** weights (`with-gh`, `without-gh`), aby v každém scénáři bylo vážení rozumné.

### 4.3 Závěr simulace

| Scénář | Engine compute | CW kvalita | Flow metrics | Reports |
|---|---|---|---|---|
| V2 + `gh` | ✅ Identical | ✅ 100 % | ✅ 100 % | ✅ Identical |
| V2 bez `gh` (solo dev) | ✅ Works | ✅ ~95 % (commit + yaml signály dominují) | ✅ 100 % | ✅ Works |
| V2 bez `gh` (small team, PR workflow) | ✅ Works | ⚠️ **60-70 %** (review-only role neviditelný) | ✅ 100 % | ⚠️ Underreports review work |
| V2 bez `gh` (large team, formal review) | ✅ Works | ❌ **40-50 %** (reviewer-heavy contribuce ztracená) | ✅ 100 % | ❌ Significant underreporting |

**Doporučení:** V2 dokumentace by měla explicitně říct "**pro plné CW signal kvalitu doporučujeme `gh auth`**" — to je honest framing. Engine "funguje offline" znamená "produce values without crash", ne "produce equally accurate values".

## 5. Tool / skill compatibility matrix (V2.0)

### 5.1 MCP tools

| Tool | V2 status | Závislost | Note |
|---|---|---|---|
| `edpa_status` | ✅ Works unchanged | YAML | — |
| `edpa_iterations` | ✅ Works unchanged | YAML | — |
| `edpa_people` | ✅ Works unchanged | YAML | — |
| `edpa_backlog` | ✅ Works unchanged | YAML | — |
| `edpa_item` | ✅ Works unchanged | YAML | — |
| `edpa_validate` | ✅ Works unchanged | YAML | — |
| `edpa_flow_metrics` | ✅ Works | YAML timestamps (V2 plní z git) | Vyžaduje `_git_timestamps.py` |
| `edpa_sync_people` | ❌ Deleted | — | Replaced by manual `people.yaml` edit |
| `edpa_item_create` (NEW) | 🆕 Planned | local counter + lock | Krok 1, 3 V2 sekvence |
| `edpa_item_update` (NEW) | 🆕 Planned | YAML | Krok 1 |
| `edpa_item_transition` (NEW) | 🆕 Planned | YAML + git timestamps | Krok 1 |
| `edpa_item_link_parent` (NEW) | 🆕 Planned | YAML | Krok 1 |
| `edpa_iteration_create` (NEW) | 🆕 Planned | YAML | Krok 1 |
| `edpa_iteration_close` (NEW) | 🆕 Planned | volá `pi_close.py` | Krok 1 |
| `edpa_people_upsert` (NEW) | 🆕 Planned | YAML | Krok 1 |

### 5.2 Skills

| Skill | V2 status | Note |
|---|---|---|
| `edpa:setup` | 🔄 Rewritten | Strip GH provisioning, init `.edpa/` + hooks |
| `edpa:add` | 🔄 Rewritten | Via MCP `edpa_item_create` |
| `edpa:sync` | ❌ **Deleted** | Replaced by git pull/push |
| `edpa:sync-people` | ❌ **Deleted** | `people.yaml` is master |
| `edpa:engine` | ⚠️ **Degraded bez `gh`** | Viz simulace 4.2 |
| `edpa:reports` | ✅ Works | Consumes engine output |
| `edpa:board` | ✅ Works unchanged | YAML-only render |
| `edpa:close-iteration` | ⚠️ Degraded bez `gh` | Závisí na engine |
| `edpa:autocalib` | ✅ Works | Synthetic corpus; **viz finding 7.3** |
| `edpa:validate` | ✅ Works unchanged | Schema check |
| `edpa:server` (NEW) | 🆕 Planned | Optional, `--with-server` flag |

### 5.3 Scripts

| Script | V2 status | Note |
|---|---|---|
| `backlog.py` | 🔄 Rewritten | `cmd_add` bez `_gh_issue_factory` |
| `sync.py` | ❌ **Deleted** | ~1800 ř. pryč |
| `_gh_issue_factory.py` | ❌ **Deleted** | — |
| `_sub_issue_linker.py` | ❌ **Deleted** | — |
| `sync_collaborators.py` | ❌ **Deleted** | — |
| `project_setup.py` | 🔄 Stripped (~1050 → ~150 ř.) | Jen init `.edpa/` struktury |
| `engine.py` | ✅ Works unchanged | Už dnes V2-clean (čte z YAML) |
| **`detect_contributors.py`** | 🔄 **CHYBÍ V PLÁNU — viz finding 7.1** | Potřebuje gh-optional + graceful fallback |
| `transitions.py` | ✅ Works | git log only |
| `yaml_edit_signals.py` | ✅ Works | git diffs |
| `pi_close.py` | ✅ Works | YAML-only |
| `board.py` | ✅ Works | YAML-only |
| `validate_syntax.py` | ✅ Works | Schema |
| `validate_iterations.py` | ✅ Works | YAML |
| `autocalibrate.py` | ✅ Works | Synthetic; finding 7.3 |
| `mcp_server.py` | 🔄 Extended | +7 write tools |
| `id_counter.py` (NEW) | 🆕 Planned | Atomic counter |
| `_git_timestamps.py` (NEW) | 🆕 Planned | created/closed_at z git |
| `validate_ids.py` (NEW) | 🆕 Planned | Pre-commit + pre-push |
| `renumber_collisions.py` (NEW) | 🆕 Planned | Auto-resolution |
| `migrate_v1_to_v2.py` (NEW) | 🆕 Planned | Migrace existujících projektů |

## 6. Rizika & mitigace

### 6.1 CW degradace bez `gh` (HIGH)

**Riziko:** Týmy s formálním PR review workflow ztratí ~50 % signálu pro reviewery, pokud `gh` chybí.

**Mitigace v plánu:**
- ADR-011: `gh` jako optional, jasně dokumentovat doporučení "pro plnou CW kvalitu zachovat `gh auth`"
- Convention `/contribute @reviewer weight:X as:reviewer` v commit msgs jako fallback
- `detect_contributors.py` musí emitnout warning při fallbacku, ne tichý degraded režim

**Akce do plánu (finding 7.2):** přidat `evidence.use_gh` konfiguraci do `edpa.yaml` schema + dokumentaci, jak ji nastavovat.

### 6.2 `detect_contributors.py` chybí v plánu (MEDIUM)

**Riziko:** Plán neuvádí, že `detect_contributors.py` se musí modifikovat pro gh-optional. Bez explicitního zařazení do "Modifikace" list se na to zapomene.

**Akce do plánu (finding 7.1):** přidat `detect_contributors.py` do "Critical files / Modifikace".

### 6.3 Autocalib weights nejsou tuned pro "no-gh" scenario (LOW)

**Riziko:** Default weights (`assignee: 4.0`, `pr_author: 3.4`, ...) předpokládají všech 5 signal typů. Bez `gh` jsou tyto váhy irelevantní, ale autocalib by je furt mohl zkoumat — což je waste cyklů.

**Akce do plánu (finding 7.3):** autocalib detekuje mode a vynechá zkoumání GH-only weights v "no-gh" profilu. Nebo má dva sets weights.

### 6.4 Server↔MCP transport (MEDIUM, již otevřené)

PI server (V2.0 optional) potřebuje volat MCP write tools. Tři varianty (spawn per request / long-lived / direct import) — žádná implementace ještě neexistuje. **Riziko**: až přijde V2.0 krok 7 (`edpa-server` skill), může se ukázat, že long-lived MCP subprocess má lifecycle problémy.

**Akce:** prototyp v V2.0 krok 7 před release; pokud problém, downgrade na "PI server čte přímo YAML, write přes spawn-per-request MCP" (porušuje invariant, ale snižuje komplexitu).

### 6.5 Migrace na sandbox repu nestestovaná (MEDIUM)

`migrate_v1_to_v2.py` zatím design, ne implementace. Migrace má 7 kroků, každý potenciálně rozbije edge case.

**Akce:** V2.0 krok 5 zahrnout E2E test migrace na sandboxu **před** smazáním GH kódu (krok 6). Migration je prerequisite, ne afterthought.

## 7. Findings — gaps v plan.md (k zapracování)

### Finding 7.1: `detect_contributors.py` do "Critical files / Modifikace"

**Současný stav:** Plán `detect_contributors.py` nezmiňuje. Implicitně se předpokládá, že "zůstane jak je", ale ADR-011 vyžaduje refactor.

**Návrh úpravy plánu:**

```diff
**Modifikace:**
+ - `plugin/edpa/scripts/detect_contributors.py` — refactor `collect_*_signals` na gh-optional pattern:
+   - `if gh_authenticated() and config.evidence.use_gh: full pipeline else: git_only_fallback()`
+   - Warning to stderr při fallbacku ("Reduced signal — gh not available, falling back to git-only evidence")
+   - V git-only fallbacku: jen `commit_author`, `manual:commit_message`, plus delegování na `yaml_edit_signals.py` a `transitions.py`
```

### Finding 7.2: `evidence.use_gh` v `edpa.yaml` schema

**Současný stav:** ADR-011 zmiňuje `edpa_config.get("evidence", {}).get("use_gh", True)`, ale plán neuvádí, kde se to zapisuje.

**Návrh úpravy plánu:**

Přidat do `edpa.yaml` schema:
```yaml
evidence:
  use_gh: true          # auto-detect → can be forced false
  warn_on_fallback: true # emit stderr when falling back to git-only
```

Default `true` — most users mají `gh auth` setup. Pro `--local-only` mode (CI bez gh) lze override.

### Finding 7.3: Autocalib mode detection

**Současný stav:** Autocalib defaultně zkoumá všech 5 signal weights. V no-gh scénáři jsou 4 z 5 weights irelevantní.

**Návrh:**

```python
# autocalibrate.py
def calibrate(mode: str = "auto"):
    if mode == "auto":
        mode = "with_gh" if gh_authenticated() else "without_gh"
    weights_to_tune = SIGNAL_WEIGHTS[mode]  # GH-only weights skipped in "without_gh"
```

Nebo: zachovat current behavior, ale v "without_gh" mode autocalib report výslovně označí GH-only weights jako "not exercised in current evidence pipeline".

### Finding 7.4: Verification section v plan.md — chybí no-gh test

**Současný stav:** Krok 8 v Verification ("End-to-end iteration close") nepokrývá scenario "bez `gh auth`".

**Návrh úpravy plánu:** přidat krok 13:

```
13. **No-gh fallback E2E**: na sandbox repu odhlásit `gh auth logout`, spustit `edpa-close-iteration` → engine produkuje cw bez crashe, warning na stderr, contributors[] obsahuje jen git-native signal typy. Resulting reports mají flag "evidence: git-only".
```

### Finding 7.5: Migration test prerequisite

**Současný stav:** Plán uvádí "krok 5: Migration skript" a "krok 6: Smazat GH kód" — ale není explicitně řečeno, že 5 MUSÍ proběhnout úspěšně před 6.

**Návrh:** v Release strategie zvýraznit:

> **Krok 5 → 6 gate:** Migration skript MUSÍ být úspěšně otestován na E2E sandbox repu + minimálně 1 reálném projektu před spuštěním kroku 6. Pokud migrace neprojde, zastavit V2.0 release.

## 8. Confidence assessment

| Oblast | Confidence | Důvod |
|---|---|---|
| MCP read tools v V2 | **HIGH** | Už dnes V2-clean, žádné GH calls |
| MCP write tools (NEW) | **MEDIUM-HIGH** | Design je solid, implementace bude přímá; idempotency key + locking pokrývají core race conditions |
| ID safety (6 vrstev) | **HIGH** | Defense in depth, každá vrstva pokrývá jiný scénář |
| Engine compute v V2 | **HIGH** | Už dnes nečte `gh` přímo, jen `contributors[]` z YAML |
| Engine evidence s `gh` | **HIGH** | Identical s dnes |
| Engine evidence bez `gh` | **MEDIUM** | Funguje, ale ~50-60 % signal redukce pro review-heavy workflows |
| Flow metrics | **HIGH** | Stačí git timestamps populated do YAML |
| Board / reports / autocalib | **HIGH** | Už dnes lokální |
| `migrate_v1_to_v2.py` | **MEDIUM** | Design rozumný, vyžaduje E2E test před release |
| PI server (V2.0 optional) | **LOW-MEDIUM** | WIP, server↔MCP transport unresolved |
| PI server (V2.x canonical) | **N/A** | Mimo V2.0 scope |
| Local hooks (pre-commit/pre-push) | **HIGH** | Standard git hook pattern, sdílí `validate_ids.py` |

**Celkový verdikt:** V2 architektura **je funkční a verifikovatelná**. Klíčová podmínka pro plnou hodnotu: ADR-011 (`gh` optional s graceful fallback) **musí být honest dokumentováno** — V2 "offline" znamená "runs", ne "runs equally well". Pro teamy s formálním PR review je `gh auth` strongly recommended.

## 9. Recommendations (souhrn)

**Před začátkem V2.0 implementace:**

1. ✅ Aktualizovat `plan.md` o findings 7.1–7.5 (`detect_contributors.py`, `evidence.use_gh` schema, autocalib mode, no-gh E2E test, migration gate)
2. ✅ Doplnit ADR-011 o explicit "Reduced signal scenarios" sekci (kdo ztrácí co)
3. 🆕 Vytvořit prototyp `detect_contributors.py` gh-optional refactoru jako proof-of-concept před V2.0 krok 1

**Během V2.0 implementace:**

4. Krok 1 (MCP write tools): testy musí pokrýt idempotency + concurrent write (V2 + V3 ADR-005 layers)
5. Krok 3 (id_counter): file lock chování ověřit cross-platform (POSIX vs. Windows)
6. Krok 5 (migration): MUSÍ projít na sandbox + 1 real projektu před krok 6
7. Krok 7 (PI server): prototyp transport před commit do design

**Po V2.0 release:**

8. Posbírat signal kvalita data ze 3-6 měsíců provozu — kolik teamů reálně runs bez `gh`
9. Pokud no-gh adoption je významná: V2.1 přidat PR-linked discussion (ADR-007 deferred) + autocalib no-gh profil

## 10. Open issues identifikované verifikací

Tyto issues neměnily V2 architekturu, ale stojí za zachycení:

- **OQ-3 (NEW):** Jak handle ID kolize v migraci? Pokud V1 repo má issue `#79` jako STO-79, ale V2 plán by chtěl resetovat counter na `max(issue_number)`, co pokud V1 mezilehlé issues byly smazány a counter má díry? → návrh: counter = max(existing IDs), díry akceptovat (jsou normální i v GH today)
- **OQ-4 (NEW):** Kdy přesně `_git_timestamps.py` spustit? Při každém `edpa_item` read (drahé) nebo lazily pri migraci a pak cache (rychlé, ale stale)? → návrh: lazy cache s invalidací při `created_at`/`closed_at` set, hot path je `git log -1 -- {file}` (~10ms)
- **OQ-5 (NEW):** Multi-repo backlog? Některé teamy mají EDPA s items rozhozenými přes několik repos. Současný `detect_contributors.py` má `repo` param. V2 fully-local model nepředpokládá multi-repo. → zachycit jako known limitation pro V2.0, případně V3.

## Reference

- [concept.md](./concept.md) — executive summary
- [plan.md](./plan.md) — implementační plán
- [decisions.md](./decisions.md) — ADRs
- [../mcp.md](../mcp.md) — současný MCP server docs
- `plugin/edpa/templates/cw_heuristics.yaml.tmpl` — signal weights
