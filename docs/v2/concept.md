# EDPA V2 — Local-First Architecture (Concept)

> **Status:** Návrh, čeká na schválení.
> **Detailní plán:** [plan.md](./plan.md)
> **Architecture Decision Records:** [decisions.md](./decisions.md)
> **Verification (signal analysis + simulace):** [verification.md](./verification.md)

## TL;DR

EDPA V2 odpojuje řízení backlogu od GitHubu. **Source of truth** zůstává `.edpa/backlog/` v gitu. **MCP server** poskytuje jediný API endpoint pro CRUD nad backlog daty. Skills, CLI commands i lokální HTTP dashboard (PI planning tool) sdílí MCP jako přístup k datům. Žádný `gh issue create`, žádný `gh project`, žádný `sync.py`. Vše běží 100 % lokálně z `git + YAML`.

Validace integrity backlogu (uniqueness ID, counter monotonie) běží **lokálně** ve třech checkpointech: MCP write → git pre-commit hook → git pre-push hook. **Žádná GH CI** — odstraňujeme i tu coupling.

## Proč to děláme

Současný EDPA je **GitHub-coupled**:

- ID schéma (`STO-42`) odvozeno z `gh issue.number` → ztráta repa = ztráta identity backlog položek
- GH Project drží custom fields (Status / Iteration / Score) → ztráta Projectu = rebuild custom fields přes `setup-refresh`
- `sync.py` (~1800 ř., ~30 % celé EDPA codebase) zajišťuje bidirectional sync YAML ↔ GH, řeší drift, conflict resolution
- Každý collaborator potřebuje `gh auth` → frikce pro nové členy + offline práce nemožná
- GH outage = EDPA outage

Vize V2: **single source of truth (git), single API layer (MCP), žádný drift, žádný sync.**

## Architektura V2

```
┌──────────────────────────────────────────────────────────────────┐
│                         git + YAML                               │
│  .edpa/backlog/{type}/*.md   .edpa/config/*.yaml                 │
│  .edpa/iterations/*.yaml     .edpa/results/*.json                │
└────────────────────────────────▲─────────────────────────────────┘
                                 │ (jediný read/write proud)
                ┌────────────────┴────────────────┐
                │       MCP server                │
                │  (mcp_server.py — rozšířený)    │
                │                                 │
                │  Read tools (8, existují dnes)  │
                │  Write tools (~7, NOVÉ)         │
                └────────────────▲────────────────┘
                                 │ stdio JSON-RPC
       ┌───────────────────┬─────┴─────┬────────────────────┐
       │                   │           │                    │
   ┌───┴────┐         ┌────┴───┐  ┌────┴─────┐       ┌──────┴──────┐
   │ Skills │         │  CLI   │  │ PI server│       │  board.py   │
   │ (LLM)  │         │ scripts│  │(optional)│       │ (read-only) │
   └────────┘         └────────┘  └──────────┘       └─────────────┘
   tenké LLM         imperativní  HTTP+React        on-demand HTML
   wrappery          příkazy      live edit UI      snapshot
```

**Pravidlo "MCP jen když dává smysl":** CRUD-shaped operace nad jednotkami dat → přes MCP. Heavy compute (engine, board render, reports) → skripty volány přímo. MCP **není povinný** mezi všemi vrstvami.

## Hlavní rozhodnutí

| Rozhodnutí | Volba |
|---|---|
| **GitHub vrstva** | Odstraněna pro sync / ID / project board / setup. `gh` smí volat **jen engine evidence pull** (read-only, optional, graceful fallback) |
| **ID generation** | `.edpa/config/id_counters.yaml` + `max(counter, fs_scan)` + file lock |
| **ID safety** | 6 lokálních vrstev: fs_scan, file lock, idempotency key, pre-save validace, pre-commit hook, pre-push hook. Žádná GH CI. |
| **MCP write surface** | 7 nových tools (item create/update/transition/link, iteration create/close, people upsert) |
| **PI planning tool** | V2.0: optional komplement (`--with-server` flag, default OFF). V2.x: canonical edit UI (později) |
| **`github:` v people.yaml** | Zachováno jako optional (pro engine PR evidence + budoucí integrace) |
| **Discussion / komentáře** | Drop — diskuze žije v PR review / Slack. (PR-linked alternativa je rezerva pro V2.1+, viz dodatek v plan.md) |
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

- **Offline-first** (let, vlak, výpadek GH)
- **Žádný `gh auth` setup** pro nové collaboratory
- **~500× rychlejší** `next_id` (bez API roundtrip)
- **~30 % redukce kódu** (`sync.py` complexity + drift bugs eliminované)
- **Deterministické testy** (žádný GH mock)
- **Portable** (GitLab, Forgejo, Gitea → fungují identicky)
- **Jednodušší DR** (žádné GH issue numbers → restore z YAML nevyžaduje renumber)
- **Plugin-based deploy** (EDPA plugin = celý systém, nic dalšího nepotřeba)

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
                ├─ Krok 4.5: detect_contributors.py gh-optional refactor + evidence.use_gh schema
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

Tři původní open questions vyřešeny (detail v [plan.md § Decisions](./plan.md#decisions-resolved-open-questions)):
- `--with-server` flag → **default OFF**, hint během install
- `github:` field v `people.yaml` → **zachovat** jako optional
- Engine evidence z `gh` → **optional s graceful fallback** (jediná `gh` cesta v EDPA, mimo sync/ID/board)

Zbývající open questions:
- **Server↔MCP transport** (PI server jak volá MCP server): long-lived subprocess vs. spawn-per-request → návrh long-lived
- **Multi-user koordinace**: explicitně pojmenovat, že V2.0 nemá shared server, `git pull` je sync mechanismus pro tým

## Reference

- **Detailní plán implementace:** [plan.md](./plan.md)
- **Architecture Decision Records:** [decisions.md](./decisions.md) — proč jsme zvolili, co jsme zvolili (11 ADRs)
- **Předchozí migration doc (V1.x):** [../migration-v2.md](../migration-v2.md) (zachovat jako historický odkaz)
- **EDPA MCP server současný stav:** [../mcp.md](../mcp.md)
- **Plugin marketplace:** `.claude-plugin/marketplace.json`
