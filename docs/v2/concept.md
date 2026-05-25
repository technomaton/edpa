# EDPA V2 — Local-First Architecture (Concept)

> **Status:** Návrh, čeká na schválení.
> **Detailní plán:** [plan.md](./plan.md)
> **Architecture Decision Records:** [decisions.md](./decisions.md)
> **Verification (signal analysis + simulace):** [verification.md](./verification.md)

## TL;DR

EDPA V2 odpojuje řízení backlogu od GitHubu. **Source of truth** zůstává `.edpa/backlog/` v gitu. **MCP server** poskytuje jediný API endpoint pro CRUD nad backlog daty. Skills, CLI commands i lokální HTTP dashboard (PI planning tool) sdílí MCP jako přístup k datům. Žádný `gh issue create`, žádný `gh project`, žádný `sync.py`. **Engine je 100 % lokální** — žádný runtime `gh` call.

GH-specifické signály pro CW (PR review, comment, assignee) se materializují do gitu přes **platform-specific CI workflow** (GH Action / GitLab CI / Forgejo Action) — deterministický skript commituje PR data přímo do YAML. Komunikace mezi engine a CI **jen přes git**, žádné API.

Validace integrity backlogu (uniqueness ID, counter monotonie) běží **lokálně** ve třech checkpointech: MCP write → git pre-commit hook → git pre-push hook. **Žádná GH CI pro ID safety** — i tu coupling odstraňujeme.

## Proč to děláme

Současný EDPA je **GitHub-coupled**:

- ID schéma (`STO-42`) odvozeno z `gh issue.number` → ztráta repa = ztráta identity backlog položek
- GH Project drží custom fields (Status / Iteration / Score) → ztráta Projectu = rebuild custom fields přes `setup-refresh`
- `sync.py` (~1800 ř., ~30 % celé EDPA codebase) zajišťuje bidirectional sync YAML ↔ GH, řeší drift, conflict resolution
- Každý collaborator potřebuje `gh auth` → frikce pro nové členy + offline práce nemožná
- GH outage = EDPA outage

Vize V2: **single source of truth (git), single API layer (MCP), žádný drift, žádný sync.**

## Architektura V2

Dvě jasně oddělené vrstvy. **Layer A je universal a 100 % lokální. Layer B je platform-specific a optional.**

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER A: Engine + Tools (universal, local-only, žádný gh)               │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                         git + YAML                                 │  │
│  │  .edpa/backlog/{type}/*.md   .edpa/config/*.yaml                   │  │
│  │  .edpa/iterations/*.yaml     .edpa/results/*.json                  │  │
│  └────────────────────────────────▲───────────────────────────────────┘  │
│                                   │ (jediný read/write proud)            │
│                  ┌────────────────┴────────────────┐                     │
│                  │       MCP server                │                     │
│                  │  Read tools (8) + Write tools (7, NOVÉ)               │
│                  └────────────────▲────────────────┘                     │
│                                   │ stdio JSON-RPC                       │
│         ┌───────────────────┬─────┴─────┬────────────────────┐           │
│     ┌───┴────┐         ┌────┴───┐  ┌────┴─────┐       ┌──────┴──────┐    │
│     │ Skills │         │  CLI   │  │ PI server│       │  board.py   │    │
│     │ (LLM)  │         │ scripts│  │(optional)│       │ (read-only) │    │
│     └────────┘         └────────┘  └──────────┘       └─────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ (Layer B commits do gitu, Layer A čte)
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER B: Platform CI Materialization (per-platform, optional)           │
│                                                                          │
│  GH:      .github/workflows/edpa-contribution-sync.yml                   │
│  GitLab:  .gitlab-ci.yml job edpa-sync           [V2.x]                  │
│  Forgejo: .forgejo/workflows/...                 [V2.x]                  │
│                                                                          │
│  Trigger: PR opened/synchronize/closed,                                  │
│           pull_request_review submitted, issue_comment created           │
│                                                                          │
│  Runs: sync_pr_contributions.py (deterministic Python, žádný LLM)        │
│  Output: commit do .edpa/backlog/{type}/{ID}.md s pr_review/comment/...  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Klíčové invarianty:**
- Layer A nikdy nezavolá Layer B (žádné runtime gh)
- Layer B nikdy nemění strukturu YAML — jen aktualizuje `contributors[]` block
- Komunikace **pouze přes git** (Layer B commituje, Layer A čte při příštím `git pull`)
- Bez Layer B (projekty bez CI) Layer A pořád běží — jen redukovaný signál

**Pravidlo "MCP jen když dává smysl":** CRUD-shaped operace nad jednotkami dat → přes MCP. Heavy compute (engine, board render, reports) → skripty volány přímo. MCP **není povinný** mezi všemi vrstvami.

## Hlavní rozhodnutí

| Rozhodnutí | Volba |
|---|---|
| **GitHub coupling** | **Žádný runtime gh dependency.** Engine + tools jsou 100 % lokální. GH integration je separate optional CI layer (per [ADR-012](./decisions.md#adr-012-platform-specific-ci-materialization-layer)). |
| **CI materialization layer** | Platform-specific deterministický skript (GH Action / GitLab CI / Forgejo Action) commituje PR signály (review, comment, assignee) přímo do YAML. Engine je čte odtud, nikoli z API. |
| **ID generation** | `.edpa/config/id_counters.yaml` + `max(counter, fs_scan)` + file lock |
| **ID safety** | 6 lokálních vrstev: fs_scan, file lock, idempotency key, pre-save validace, pre-commit hook, pre-push hook. Žádná GH CI pro ID safety. |
| **MCP write surface** | 7 nových tools (item create/update/transition/link, iteration create/close, people upsert) |
| **PI planning tool** | V2.0: optional komplement (`--with-server` flag, default OFF). V2.x: canonical edit UI (později) |
| **`github:` v people.yaml** | Zachováno jako optional (mapping GH login → person pro CI materialization) |
| **Discussion / komentáře** | Drop — diskuze žije v PR review / Slack. (PR-linked alternativa rezerva pro V2.1+) |
| **Timestamps** | `created_at` / `updated_at` / `closed_at` derivovány z git logu, ne z GH API |
| **Release strategy** | Hard cut: V1 archivován jako `v1-github-coupled` větev + tag, main = V2.0 |
| **Migrace existujících projektů** | `migrate_v1_to_v2.py` skript: pull final state, seed counter, backfill timestamps, strip sync config, instalace hooks |

## Co se ztrácí (vědomě)

- GH Issues UI (browse, mention, link z PR)
- GH Project board (drag-drop status v UI)
- GH notifications (email na assign / mention)
- Cross-repo issue refs (`org/other-repo#42`)
- Native sub-issues (parent/child už máme v YAML, ale bez GH UI render)
- 3rd-party integrace (Slack-GH bridge, Linear sync, ...)
- Inline discussion threads na issue

## Co se získává

- **Offline-first engine** — Layer A je 100 % lokální, nikdy nevolá `gh`. Žádný runtime decision tree, jediná cesta kódu.
- **Žádný `gh auth` setup** pro developery — CI Action má vlastní token
- **~500× rychlejší** `next_id` (bez API roundtrip)
- **~30 % redukce kódu** (`sync.py` complexity + drift bugs eliminované)
- **Deterministické testy** (žádný GH mock; CI materialization sama je deterministická)
- **Portable plně přes per-platform CI adapter** — stejný Python skript pro GH / GitLab / Forgejo, jen tenký workflow wrapper
- **Jednodušší DR** (evidence v gitu trvale, ne v ephemeral GH API state)
- **Plugin-based deploy** (EDPA plugin = celý systém, nic dalšího nepotřeba)
- **Žádné "honest framing" caveat** — V2 + CI = zero regression vs V1; bez CI = explicit opt-in trade-off, ne hidden limitation

## Migration overview

Pro existující GH-coupled projekty:

```
v1.x  ──┐
        ├──► tag: v1.23.x-final  ─►  větev: v1-github-coupled (záloha)
        │
        └──► main: pokračuje V2 vývojem
                │
                ├─ Krok 1:  přidat MCP write tools (bez odstranění čehokoliv)
                ├─ Krok 2:  refactor edpa-add na MCP
                ├─ Krok 3:  id_counter.py (+ file lock) + _git_timestamps.py
                ├─ Krok 4:  validate_ids.py + renumber_collisions.py + git hooks
                ├─ Krok 4.5: CI materialization layer — sync_pr_contributions.py
                │            + .github/workflows/edpa-contribution-sync.yml
                │            + detect_contributors.py refactor na čistě git-native
                ├─ Krok 5:  migrate_v1_to_v2.py + E2E test na sandboxu
                │   ├── Gate: migrace MUSÍ projít před krokem 6 ──┐
                ├─ Krok 6:  smazat GH kód (BREAKING) ◀────────────┘
                ├─ Krok 7:  edpa-server skill (optional)
                └─ Release V2.0 + CHANGELOG s migration steps
```

Existující projekty spustí `migrate_v1_to_v2.py`, který:
1. Provede finální `edpa-sync pull` (poslední běh sync.py)
2. Naseeduje `id_counters.yaml` z `max(issue_number)` per type
3. Backfillne `created_at` / `closed_at` z git logu pro chybějící timestamps
4. Archivuje `issue_map.yaml` do `.edpa/archive/`
5. Vystřihne `sync:` blok z `edpa.yaml`
6. Vytvoří jeden migration commit

GH Project se nedeletuje, jen unlinkne — pro historický audit.

## Stav rozhodnutí

Vyřešeno (detail v [decisions.md](./decisions.md)):
- `--with-server` flag → **default OFF**, hint během install (ADR-009)
- `github:` field v `people.yaml` → **zachovat** jako optional (ADR-010)
- Engine evidence z `gh` → **ADR-011 superseded by ADR-012** → engine je 100 % lokální, GH signály přes CI materialization

Zbývající open questions (V2.0):
- **Server↔MCP transport** (PI server jak volá MCP server): long-lived subprocess vs. spawn-per-request → návrh long-lived
- **Multi-user koordinace**: V2.0 nemá shared server, `git pull` je sync mechanismus pro tým
- **CI materialization timing** (per ADR-012): `mode: merge-only` default (clean PR history) vs. `mode: live` opt-in (real-time audit trail)
- **CI item resolution priority**: PR title regex vs. body vs. modified files vs. branch name → union se signál-splitting heuristikou
- **Fork PRs handling**: Action skipuje fork PRs (permissions), materializace odložena do `pull_request:closed` (merged) v main contextu

## Reference

- **Detailní plán implementace:** [plan.md](./plan.md)
- **Architecture Decision Records:** [decisions.md](./decisions.md) — proč jsme zvolili, co jsme zvolili (12 ADRs)
- **Předchozí migration doc (V1.x):** [../migration-v2.md](../migration-v2.md) (zachovat jako historický odkaz)
- **EDPA MCP server současný stav:** [../mcp.md](../mcp.md)
- **Plugin marketplace:** `.claude-plugin/marketplace.json`
