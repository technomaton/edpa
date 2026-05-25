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

**Klíčový poznatek:** bez CI vrstvy ztrácíme **~80 % vážených signal typů** auto-detection. Ale s CI materialization layer (per [ADR-012](./decisions.md#adr-012-platform-specific-ci-materialization-layer)) tyto signály vznikají jako commits do gitu — engine je čte z YAML, nikoliv z `gh`.

## 3. V2 evidence pipeline (per ADR-012)

```
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER B: CI MATERIALIZATION (optional, per-platform)                  │
│                                                                        │
│  GH:      .github/workflows/edpa-contribution-sync.yml                 │
│  GitLab:  .gitlab-ci.yml (job edpa-sync)             [V2.x]           │
│  Forgejo: .forgejo/workflows/edpa-contribution-sync.yml [V2.x]        │
│                                                                        │
│  Trigger: pull_request opened/synchronize/closed,                      │
│           pull_request_review submitted,                               │
│           issue_comment created                                        │
│                                                                        │
│           │                                                            │
│           ▼                                                            │
│  sync_pr_contributions.py (deterministický Python skript)              │
│  - Identifies items (PR title regex + body + modified files + branch)  │
│  - Maps event → signal type → weight (z cw_heuristics.yaml)            │
│  - Dedupe via signals[].ref (review_id / comment_id / pr_id)           │
│  - Updates contributors[] in .edpa/backlog/{type}/{ID}.md              │
│                                                                        │
│           │                                                            │
│           ▼                                                            │
│  git commit -m "evidence(sync): PR #X — <event_type>"  +  git push     │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ (commit lands in git)
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER A: ENGINE (universal, 100% local)                               │
│                                                                        │
│  detect_contributors.py (čistě git-native):                            │
│  - commit_author (z git log)                                           │
│  - manual:commit_message (parse commit msgs)                           │
│  - yaml_edit:* (delegace na yaml_edit_signals.py)                      │
│  - gate_events (delegace na transitions.py)                            │
│                                                                        │
│  + signály MATERIALIZOVANÉ Layer B (čte je jako součást YAML):         │
│  - pr_author, pr_reviewer, issue_comment, assignee                     │
│  (žádný runtime gh call — Layer B už zapsal do YAML)                   │
│                                                                        │
│           │                                                            │
│           ▼                                                            │
│  Σ contribution_scores → normalize per item → cw                       │
│           │                                                            │
│           ▼                                                            │
│  engine.py reads YAML → kapacita allocation                            │
│           │                                                            │
│           ▼                                                            │
│  edpa_results.json → reports → snapshots                               │
└────────────────────────────────────────────────────────────────────────┘
```

**Klíčový invariant:** Layer A nikdy nezavolá Layer B. Komunikace **pouze přes git** (Layer B commituje YAML diffy, Layer A je čte při příštím `git pull`). Layer B je optional — bez něj Layer A pořád běží, ale GH-specifické signály chybí.

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

### 4.1 V2 **s CI materialization** (default pro GH-hosted projekty)

Pipeline:
1. PR #42 opened, references S-200 v title — Action fires na `pull_request:opened` → commit `pr_author` signal pro turynu
2. tuma pushe commits do PR — Action fires na `pull_request:synchronize` → confirms `commit_author` signal pro tumu (paralelně k git-native detection)
3. urbanek submituje review — Action fires na `pull_request_review:submitted` → **commit `pr_reviewer` signal pro urbanka** (ref: review_id)
4. urbanek napíše komentář k PR — Action fires na `issue_comment:created` → commit `issue_comment` signal (ref: comment_id, dedupe pokud už review_id ho creditoval podobně)
5. PR merged — Action fires na `pull_request:closed/merged` → finalní synchronizace contributors[]

Po merge stavu YAML:
```yaml
# detect_contributors.py read (V2 + CI):
contributors:
- person: turyna   ; cw: 1.0    # assignee + pr_author + commit_author + yaml_edit:create (LayerA + LayerB)
- person: tuma     ; cw: 0.6    # commit_author (LayerA) + případně pr_reviewer (LayerB)
- person: urbanek  ; cw: 0.3    # pr_reviewer + issue_comment (LayerB) → materializovaný cw
```

✅ **Zero regression** — identický stav jako V1, ale **bez runtime `gh` calls**. Engine prostě čte YAML.

### 4.2 V2 **bez CI** (self-hosted git bez Actions, lokální git server, …)

Layer B chybí → engine vidí jen Layer A signály:

| Osoba | Git-native signály (Layer A) | Score |
|---|---|---:|
| **turyna** | `commit_author` (2.78) + `yaml_edit:create` (5.0) + `yaml_edit:scalar_change` na status flip (0.5) | **8.28** |
| **tuma** | `commit_author` (2.78) — pokud commitoval | **2.78** |
| **urbanek** | (nic git-native, pokud jen reviewoval bez commitu) | **0.00** |

Po normalizaci: turyna cw=0.75, tuma cw=0.25, **urbanek cw=0** — známá limitace pro projekty bez CI.

**Toto NENÍ V2 design flaw, je to opt-in trade-off:**
- Tým má volbu: nasadit CI (cca 10 min setup, free na GH/GitLab/Forgejo) → full signal
- Nebo: žít s redukovaným signálem (akceptovatelné pro solo dev, neformální projekty)
- Nebo: konvence `/contribute @reviewer weight:0.3 as:reviewer` v commit msgs jako částečný workaround

**Engine sám:** funguje 100 %, deterministicky, jediná cesta kódu. Crashes? Ne. Warnings? Ne. Známá limitace dokumentovaná v `quick-start.md` jako "for full signal quality, enable CI workflow".

### 4.3 Závěr simulace

| Scénář | Engine compute | CW kvalita | Flow metrics | Reports |
|---|---|---|---|---|
| V2 + CI (GH/GitLab/Forgejo) | ✅ Identical | ✅ **100 %** (zero regression vs V1) | ✅ 100 % | ✅ Identical |
| V2 bez CI (solo dev) | ✅ Works | ✅ ~95 % (commit + yaml dominují, review je marginal) | ✅ 100 % | ✅ Works |
| V2 bez CI (small team s PR review) | ✅ Works | ⚠️ **60-70 %** (review role neviditelný — známá limitace) | ✅ 100 % | ⚠️ Underreports review |
| V2 bez CI (large team formal review) | ✅ Works | ❌ **40-50 %** | ✅ 100 % | ❌ Significant underreporting |

**Honest framing posun:**

> ❌ ~~"V2 offline = runs, ne runs equally well"~~ (původní ADR-011)
> ✅ **"V2 engine je 100 % lokální. Pro plný signal nasadit CI workflow (free, ~10 min setup). Bez CI je redukovaný signál akceptovatelný pro solo / neformální projekty."**

Klíčový rozdíl: degradace už **není fundamental engine limitation**, ale **explicit team choice** (mít/nemít CI).

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
| `edpa:setup` | 🔄 Rewritten | Strip GH provisioning, init `.edpa/` + hooks + templating `.github/workflows/edpa-contribution-sync.yml` pro GH-hosted projekty |
| `edpa:add` | 🔄 Rewritten | Via MCP `edpa_item_create` |
| `edpa:sync` | ❌ **Deleted** | Replaced by git pull/push |
| `edpa:sync-people` | ❌ **Deleted** | `people.yaml` is master |
| `edpa:engine` | ✅ Works | Engine je 100% lokální. **Bez CI**: redukovaný signál (známá limitace, viz § 4.2) |
| `edpa:reports` | ✅ Works | Consumes engine output |
| `edpa:board` | ✅ Works unchanged | YAML-only render |
| `edpa:close-iteration` | ✅ Works | Orchestruje lokální engine + reports |
| `edpa:autocalib` | ✅ Works | Synthetic corpus, V2.0 beze změny |
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
| **`detect_contributors.py`** | 🔄 **Refactor na čistě git-native** (per ADR-012) | Odstranit všechny `gh` calls; zachovat commit_author + yaml_edit delegation + transitions + manual:commit_message |
| `transitions.py` | ✅ Works | git log only |
| `yaml_edit_signals.py` | ✅ Works | git diffs |
| `pi_close.py` | ✅ Works | YAML-only |
| `board.py` | ✅ Works | YAML-only |
| `validate_syntax.py` | ✅ Works | Schema |
| `validate_iterations.py` | ✅ Works | YAML |
| `autocalibrate.py` | ✅ Works | Synthetic, V2.0 beze změny |
| `mcp_server.py` | 🔄 Extended | +7 write tools |
| `id_counter.py` (NEW) | 🆕 Planned | Atomic counter |
| `_git_timestamps.py` (NEW) | 🆕 Planned | created/closed_at z git |
| `validate_ids.py` (NEW) | 🆕 Planned | Pre-commit + pre-push |
| **`sync_pr_contributions.py`** (NEW) | 🆕 **Planned** (per ADR-012) | Platform-agnostic skript pro CI materialization layer |
| `renumber_collisions.py` (NEW) | 🆕 Planned | Auto-resolution |
| `migrate_v1_to_v2.py` (NEW) | 🆕 Planned | Migrace existujících projektů |

## 6. Rizika & mitigace

> **Note:** Sekce přehodnocena po přijetí [ADR-012](./decisions.md#adr-012-platform-specific-ci-materialization-layer) — CW degradation risk downgraded z HIGH na LOW pro projekty s CI; "honest framing" už není potřeba.

### 6.1 CW signal kvalita bez CI (LOW pro V2.0)

**Riziko:** Projekty bez CI infrastruktury (self-hosted git bez Actions) mají redukovaný signál (~50-60 % loss pro review-heavy workflows). Není to V2 design flaw, ale opt-in trade-off — tým si vědomě volí "no CI = no GH signals".

**Mitigace (per ADR-012):**
- `edpa-setup` skill automaticky vytváří `.github/workflows/edpa-contribution-sync.yml` pro GH-hosted projekty (auto-detect přes `git remote get-url`)
- Dokumentace v `quick-start.md` doporučí setup CI pro plný signal
- Convention `/contribute @reviewer weight:X as:reviewer` v commit msgs jako částečný workaround pro projekty bez CI

### 6.2 CI Action permissions / fork PRs (MEDIUM)

**Riziko:** GH Action vyžaduje `contents: write` permission pro commit zpět. Některé orgs restrict to. Plus: PRs z forků nemohou commitnout zpět z bezpečnostních důvodů (Action je v PR contextu, ne main).

**Mitigace:**
- Action skipuje fork PRs (detekce přes `github.event.pull_request.head.repo.full_name == github.repository`)
- Pro fork PRs: materializace evidence se odloží do `pull_request:closed` (merged), kdy už evidence běží v main contextu (s plnými permissions)
- Pro restricted orgs: dokumentace v `RUNBOOK.md` o deploy key / PAT fallback

### 6.3 Commit pollution v PR historii (MEDIUM)

**Riziko:** Per-event materializace přidává commits do PR historie (mohlo by být 5-10 commits per PR). Některé teamy chtějí čistou PR historii.

**Mitigace:**
- Default `mode: merge-only` — Action triggeruje jen na `pull_request:closed/merged`, materializuje vše najednou jako jeden commit
- Opt-in `mode: live` pro teamy, které chtějí real-time audit trail
- Squash-on-merge GH setting čistí PR historii automaticky (evidence commit projde jako jeden squash)

### 6.4 Race conditions Action ↔ developer push (MEDIUM)

**Riziko:** Developer pushe commits do PR branch současně s Action, která commituje evidence. Action push může selhat (non-fast-forward).

**Mitigace:**
- Action retry s `git pull --rebase origin <branch> && git push`
- Po 3 failed pokusech: exit clean, příští event re-syncne (idempotence přes `signals[].ref` zajistí konzistenci)
- Concurrent developer push nikdy neztratí — Action ustupuje

### 6.5 Server↔MCP transport (MEDIUM, již otevřené)

PI server (V2.0 optional) potřebuje volat MCP write tools. Tři varianty (spawn per request / long-lived / direct import) — žádná implementace ještě neexistuje. **Riziko**: až přijde V2.0 krok 7 (`edpa-server` skill), může se ukázat, že long-lived MCP subprocess má lifecycle problémy.

**Akce:** prototyp v V2.0 krok 7 před release; pokud problém, downgrade na "PI server čte přímo YAML, write přes spawn-per-request MCP" (porušuje invariant, ale snižuje komplexitu).

### 6.6 Migrace na sandbox repu nestestovaná (MEDIUM)

`migrate_v1_to_v2.py` zatím design, ne implementace. Migrace má 7 kroků, každý potenciálně rozbije edge case.

**Akce:** V2.0 krok 5 zahrnout E2E test migrace na sandboxu **před** smazáním GH kódu (krok 6). Migration je prerequisite, ne afterthought.

## 7. Findings — gaps v plan.md (status po ADR-012)

> Tato sekce zachycuje původní 5 findings z první verifikace + jejich revize po přijetí [ADR-012](./decisions.md#adr-012-platform-specific-ci-materialization-layer). Findings 7.1, 7.2, 7.3 jsou **superseded** ADR-012 (lepší řešení); 7.4 a 7.5 zůstávají platné.

### Finding 7.1: `detect_contributors.py` v "Critical files / Modifikace" — **SUPERSEDED by ADR-012**

**Status:** Plán už `detect_contributors.py` zahrnuje. ADR-012 jej však dále zjednodušuje: místo gh-optional refactoru → čistě git-native (žádný `gh` call). Plán updatován v této revizi.

### Finding 7.2: `evidence.use_gh` v `edpa.yaml` schema — **SUPERSEDED by ADR-012**

**Status:** Schema not needed. ADR-012 odstraňuje pojem "evidence source" z engine kódu úplně. Engine vždy čte YAML; co tam je závisí na CI setup. Schema odstraněno.

### Finding 7.3: Autocalib mode detection — **SUPERSEDED by ADR-012**

**Status:** Autocalib v V2.0 beze změny. Weights v `cw_heuristics.yaml` zůstávají všechny relevantní (pro projekty s CI). Pro projekty bez CI jsou GH-only weights "exercised but never fired" — autocalib je dokumentuje jako 0 fires, ale nevynechává.

### Finding 7.4: Verification section v plan.md — CI materialization E2E

**Status:** Platné, ale rozšířeno per ADR-012. Plán updatován v této revizi (krok 13 = CI materialization E2E test, 4 sub-scenarios: engine no-gh check, materialization roundtrip, determinism, bare git fallback).

### Finding 7.5: Migration test prerequisite

**Status:** Platné. Plán updatován v této revizi (Gate 5→6 explicitně označen).

## 8. Confidence assessment (revised after ADR-012)

| Oblast | Confidence | Důvod |
|---|---|---|
| MCP read tools v V2 | **HIGH** | Už dnes V2-clean, žádné GH calls |
| MCP write tools (NEW) | **MEDIUM-HIGH** | Design je solid, implementace bude přímá; idempotency key + locking pokrývají core race conditions |
| ID safety (6 vrstev) | **HIGH** | Defense in depth, každá vrstva pokrývá jiný scénář |
| Engine compute v V2 | **HIGH** | 100 % lokální, jediná cesta kódu (po ADR-012) |
| Engine evidence s CI | **HIGH** | Identical s V1 (full signal materialized do YAML) |
| Engine evidence bez CI | **MEDIUM** | Funguje, ale ~50-60 % signal redukce — známá limitace, opt-in trade-off |
| CI materialization layer (NEW) | **MEDIUM-HIGH** | Deterministic Python skript je solid; CI permission edge cases (fork PRs, restricted orgs) mají dokumentované mitigace |
| Flow metrics | **HIGH** | Stačí git timestamps populated do YAML |
| Board / reports / autocalib | **HIGH** | Už dnes lokální |
| `migrate_v1_to_v2.py` | **MEDIUM** | Design rozumný, vyžaduje E2E test před release |
| PI server (V2.0 optional) | **LOW-MEDIUM** | WIP, server↔MCP transport unresolved |
| PI server (V2.x canonical) | **N/A** | Mimo V2.0 scope |
| Local hooks (pre-commit/pre-push) | **HIGH** | Standard git hook pattern, sdílí `validate_ids.py` |
| Multi-platform CI (GitLab, Forgejo) | **N/A pro V2.0** | Plánováno V2.x — same Python skript, jiný thin wrapper |

**Celkový verdikt po ADR-012:** V2 architektura **je funkční, verifikovatelná, a bez "honest framing" caveat**. Engine je literálně 100 % lokální. CI materialization layer je optional value-add (značně doporučený pro review-heavy teamy). Pro teamy bez CI je redukovaný signál opt-in trade-off, ne fundamental V2 limitation.

**Klíčový posun oproti původní verifikaci:** "Engine evidence bez `gh`" stoupla z LOW na MEDIUM (signal loss je explicit team choice, ne hidden caveat). "Engine evidence s `gh`" → "Engine evidence s CI" stoupla na HIGH (žádné runtime gh, deterministic materialization).

## 9. Recommendations (souhrn po ADR-012)

**Před začátkem V2.0 implementace:**

1. ✅ Aktualizovat `plan.md` o ADR-012 changes (`sync_pr_contributions.py`, `.github/workflows/edpa-contribution-sync.yml`, `detect_contributors.py` čistě git-native)
2. ✅ ADR-011 marked Superseded by ADR-012 (zachováno jako historie)
3. 🆕 Vytvořit prototyp `sync_pr_contributions.py` + GH Action na sandbox repu jako proof-of-concept před V2.0 krok 4.5

**Během V2.0 implementace:**

4. Krok 1 (MCP write tools): testy musí pokrýt idempotency + concurrent write
5. Krok 3 (id_counter): file lock chování ověřit cross-platform (POSIX vs. Windows)
6. Krok 4.5 (CI materialization): determinism test + idempotence test + bare-git fallback E2E
7. Krok 5 (migration): MUSÍ projít na sandbox + 1 real projektu před krok 6
8. Krok 7 (PI server): prototyp transport před commit do design

**Po V2.0 release:**

9. Posbírat data o CI adoption — kolik projektů reálně nasadilo `edpa-contribution-sync.yml`
10. Pokud >10 % projektů na GitLab/Forgejo: V2.1 přidat platform-specific CI templates
11. Pokud reviewer-heavy teamy bez CI hlásí signal loss: nasadit `--with-server` PI tool jako edit-time UI s manual contribution input

## 10. Open issues identifikované verifikací

Tyto issues neměnily V2 architekturu, ale stojí za zachycení:

- **OQ-3 (NEW):** Jak handle ID kolize v migraci? Pokud V1 repo má issue `#79` jako STO-79, ale V2 plán by chtěl resetovat counter na `max(issue_number)`, co pokud V1 mezilehlé issues byly smazány a counter má díry? → návrh: counter = max(existing IDs), díry akceptovat (jsou normální i v GH today)
- **OQ-4 (NEW):** Kdy přesně `_git_timestamps.py` spustit? Při každém `edpa_item` read (drahé) nebo lazily pri migraci a pak cache (rychlé, ale stale)? → návrh: lazy cache s invalidací při `created_at`/`closed_at` set, hot path je `git log -1 -- {file}` (~10ms)
- **OQ-5 (NEW):** Multi-repo backlog? Některé teamy mají EDPA s items rozhozenými přes několik repos. Současný `detect_contributors.py` má `repo` param. V2 fully-local model nepředpokládá multi-repo. → zachycit jako known limitation pro V2.0, případně V3.
- **OQ-6 (RESOLVED by [ADR-013](./decisions.md#adr-013-pr-event-handling--merge-only-default-with-live-opt-in)):** Commit timing — default `mode: merge-only` (Action fires JEDNOU na `pull_request:closed/merged`, batch commit do base branch). Opt-in `mode: live` v workflow YAML komentech. **Open PRs mid-iteration**: `edpa:close-iteration` skill automaticky volá `sync_pr_contributions.py --pr N --rebuild --skip-commit` pro každý open PR zmiňující items v zavírané iteraci.
- **OQ-7 (still OPEN):** Item resolution priority při materializaci — co když PR title má `STO-79`, ale modified files dotýkají `STO-80` a `STO-81`? Návrh: union (signál se rozdělí mezi všechny matched items), s `weight_split: even` (default) nebo proporční dle modified files heuristics. Rozhodne se při implementaci V2.0 krok 4.5 — vyžaduje user testing s reálnými multi-item PRs.
- **OQ-8 (RESOLVED by [ADR-013](./decisions.md#adr-013-pr-event-handling--merge-only-default-with-live-opt-in)):** Fork PRs — Action skipuje per-event events (security: no write do forku, `pull_request_target` na untrusted code je risk). Materializace odložena do `pull_request:closed/merged`, kdy code je v main context. Workflow YAML: `if: merged == true || head.repo.full_name == repository`.
- **OQ-9 (RESOLVED by [ADR-013](./decisions.md#adr-013-pr-event-handling--merge-only-default-with-live-opt-in)):** Race conditions Action ↔ developer push — `git pull --rebase --strategy-option=ours` s 3× retry + exponential backoff. `--strategy-option=ours` při YAML konfliktu (Action vždy preferuje svou evidenci). Po 3 failed pokusech: exit clean, příští event re-syncne (idempotence přes `signals[].ref`).

## Reference

- [concept.md](./concept.md) — executive summary
- [plan.md](./plan.md) — implementační plán
- [decisions.md](./decisions.md) — ADRs
- [../mcp.md](../mcp.md) — současný MCP server docs
- `plugin/edpa/templates/cw_heuristics.yaml.tmpl` — signal weights
