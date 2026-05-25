# EDPA V2 — Local-First Architecture (Detailní plán)

> **Status:** Návrh, čeká na schválení.
> **Concept overview:** [concept.md](./concept.md)
> **Architecture Decision Records:** [decisions.md](./decisions.md)
> **Verification (signal analysis + simulace):** [verification.md](./verification.md)

## Context

EDPA je dnes GH-coupled: ID schéma (`STO-42`) odvozuje z `gh issue.number`, Project board drží custom fields (Status/Iteration/Score), `sync.py` (~1800 ř.) zajišťuje bidirectional sync YAML ↔ GH. To přináší dva problémy:

1. **Fragilita DR** — ztráta repa = nepřenositelná čísla (GH nedovolí force-set issue number); ztráta Projectu = rebuild custom fields (řeší `setup-refresh`, ale s GAP).
2. **Auth/network coupling** — každý collaborator potřebuje `gh auth`, EDPA nefunguje offline, GH outages = EDPA outages, ~30 % komplexity v `sync.py` řeší drift mezi YAML a GH state.

**Trigger:** vize **MCP jako jediná API vrstva nad YAML**, GitHub kompletně odstraněn. Skills, lokální HTTP server (PI planning tool) i CLI sdílí MCP jako přístup k datům. Existující PI planning tool (`tools/pi-planning/`, Express+React, WIP) je vzor lokálního dashboardu.

**Outcome:** EDPA běží 100 % lokálně z git+YAML. Žádný `gh` ve scriptech. MCP poskytuje strukturovaný CRUD. UI buď on-demand HTML (board.py) nebo lokální server (PI tool). Vendoring přes `install.sh` ze stejného plugin balíčku.

## Cílová architektura

```
┌──────────────────────────────────────────────────────────────────┐
│                         git + YAML                               │
│  .edpa/backlog/{type}/*.md   .edpa/config/*.yaml                 │
│  .edpa/iterations/*.yaml     .edpa/results/*.json                │
└────────────────────────────────▲─────────────────────────────────┘
                                 │ (jediný zápis/čtení projde tudy)
                ┌────────────────┴────────────────┐
                │       MCP server                │
                │  (mcp_server.py — rozšířený)    │
                │                                 │
                │  Read tools (8, dnes)           │
                │  Write tools (~7, NOVÉ)         │
                │  Compute tools (call scripts)   │
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

**Co je pryč:** žádné `gh` volání, žádný `sync.py`, žádný `_gh_issue_factory.py`, žádný `_sub_issue_linker.py`, žádné GH Projects, žádný `edpa-sync` / `edpa-sync-people` skill.

## Pravidlo: kdy přes MCP, kdy přímo script

MCP **není povinný** mezi všemi vrstvami. Aplikuj toto rozhodnutí:

| Operace | Přes MCP | Důvod |
|---|---|---|
| Create / update / transition item | ✓ | Strukturovaný CRUD, validace, generování ID |
| Read item / backlog / status / people | ✓ | Jediná shape pro UI + skills + CLI |
| Iteration CRUD + close | ✓ | CRUD-shaped |
| People upsert | ✓ | CRUD-shaped |
| Engine výpočet (CW, derived hours) | ✗ — script přímo | Heavy compute, vrací JSON, neopodstatněný overhead |
| Board HTML render | ✗ — script přímo | Generuje statický soubor, nevolá se ze skills často |
| Reports / snapshots | ✗ — script přímo | Heavy compute + filesystem write |
| Validate YAML schema | ✓ (už dnes je) | Lehký, často volaný z UI/CI |

Pravidlo: **MCP pro CRUD-shaped operace nad jednotkami dat** (item, iteration, person). **Přímý script pro heavy compute, render, multi-step orchestration**.

## MCP write surface — nové tools

Audit potvrdil: všech 8 současných tools je read-only (`mcp_server.py:372-745`). Pro local-first nutno přidat:

| Tool | Argumenty | Co dělá |
|---|---|---|
| `edpa_item_create` | `type`, `title`, `body?`, `parent?`, `iteration?`, `assignee?` | Volá `id_counter.next(type)` → zapíše `.edpa/backlog/{type}/{ID}.md` |
| `edpa_item_update` | `item_id`, `fields: {status?, iteration?, score?, assignee?, …}` | Atomic update YAML frontmatter |
| `edpa_item_transition` | `item_id`, `status` (Planned/InProgress/Review/Done/Cancelled) | Update status + auto-stamp `closed_at` při Done |
| `edpa_item_link_parent` | `item_id`, `parent_id` | Set `parent:` field (validace, že parent existuje a má vyšší level) |
| `edpa_iteration_create` | `id`, `start_date`, `end_date`, `type` | Zapíše `.edpa/iterations/{id}.yaml` |
| `edpa_iteration_close` | `id` | Mark closed + finalize (volá `pi_close.py` přes interní import) |
| `edpa_people_upsert` | `id`, `name`, `role`, `fte`, … | Edit `.edpa/config/people.yaml` |

Všechny vrací `TextContent(JSON)` (stejný pattern jako dnes — viz `mcp_server.py:json.dumps`).

**Existující `edpa_sync_people`** se přejmenuje na `edpa_people_list_orphans` nebo smaže (ztrácí smysl, žádný GH).

## ID schéma

`.edpa/config/id_counters.yaml`:
```yaml
counters:
  initiative: 5
  epic: 12
  feature: 34
  story: 78
  defect: 9
  event: 3
  risk: 2
```

**Display:** ID prefix se zachovává (`STO-42`, `EPI-3`, …) — stejné UX jako dnes.

## ID safety — local defense in depth

GH dnes funguje jako globální arbitr ID čísel. Bez něj jsou možné kolize:

| Typ kolize | Kdy nastane |
|---|---|
| **Cross-branch race** | Dva PRs/branch paralelně oba bumpnou counter 78→79 |
| **Same-branch race** | Dva devs na stejném branchi bez `git pull` |
| **Manual filesystem edit** | Uživatel ručně vytvoří `STO-79.md` mimo MCP |
| **Retry / double-call MCP** | Klient zopakuje `edpa_item_create` (network glitch, double-tap) |
| **Local concurrent processes** | Dva MCP klienti běží proti stejnému repu (PI server + CLI naráz) |

Žádný jeden mechanismus nepokryje vše. Návrh **6 vrstev, všechny lokální** (žádná GH CI dependency):

### Vrstva 1: `fs_scan` v `next_id` (write time)

```python
# id_counter.py
def next_id(item_type: str, root: Path) -> str:
    counter_path = root / ".edpa/config/id_counters.yaml"
    backlog_dir = root / ".edpa/backlog" / item_type

    counter_value = read_counter(counter_path, item_type)   # např. 78
    fs_max = scan_max_id_in_dir(backlog_dir, item_type)     # např. 79 (manuální edit)
    next_num = max(counter_value, fs_max) + 1               # → 80
    write_counter_atomic(counter_path, item_type, next_num)  # temp + rename
    return f"{PREFIX[item_type]}-{next_num}"
```

Odolnost: manuální edity, partial state.

### Vrstva 2: Lokální file lock (concurrent processes)

```python
with FileLock(root / ".edpa/.id_counter.lock", timeout=5):
    new_id = next_id(item_type, root)
    write_backlog_file(new_id, ...)
```

Odolnost: dva paralelní MCP procesy na stejném repu (PI server + CLI naráz).

### Vrstva 3: Idempotency key v MCP write tools

```python
# MCP tool argument:
edpa_item_create(
    type="story",
    title="...",
    idempotency_key="01HV8X..."   # ULID generated client-side
)
```

Server kontroluje `.edpa/.idempotency.log` (gitignored, 24h TTL). Pokud klíč existuje → vrátí původně vytvořené ID místo nového. Pokrývá retry/double-tap.

### Vrstva 4: Pre-save validation v MCP write tool

Před zápisem YAML do `.edpa/backlog/{type}/{ID}.md`, MCP tool validuje:
- ID match: filename ≡ frontmatter `id:`
- Žádný soubor s tímto ID dosud neexistuje (race s lockem ošetřena Vrstvou 2)
- `parent_id` (pokud zadáno) existuje a má vyšší level
- Type/status hodnoty platné dle schema

Při failnutí: žádný side-effect, error returnem do klienta.

### Vrstva 5: Pre-commit hook (před git commit)

`install.sh` instaluje:

```bash
# .git/hooks/pre-commit (symlink na .claude/edpa/hooks/pre-commit)
#!/bin/sh
exec python3 .claude/edpa/scripts/validate_ids.py --staged
```

`validate_ids.py --staged`:
- Skenuje staged soubory v `.edpa/backlog/`
- Verifikuje: filename ≡ frontmatter `id:`
- Verifikuje: žádné duplicity v rámci staged setu
- Verifikuje: counter file je monotonní (nový counter ≥ staré + počet nových položek)
- Verifikuje: žádný nový ID neexistuje na aktuálním tipu branchu (HEAD)

Při failnutí: commit zablokován, instrukce na fix.

### Vrstva 6: Pre-push hook (před git push)

`install.sh` instaluje:

```bash
# .git/hooks/pre-push (symlink na .claude/edpa/hooks/pre-push)
#!/bin/sh
remote="$1"
url="$2"
while read local_ref local_sha remote_ref remote_sha; do
    python3 .claude/edpa/scripts/validate_ids.py --pre-push \
        --remote "$remote" \
        --local-sha "$local_sha" \
        --remote-sha "$remote_sha" || exit 1
done
```

`validate_ids.py --pre-push`:
- `git fetch --quiet $remote $remote_ref` (refresh upstream view)
- Diff commits, které pushe přidá nad upstream
- Pro každý nový soubor v `.edpa/backlog/{type}/`:
  - Verifikuje, že ID NEEXISTUJE na upstream (`origin/<branch>`)
- Verifikuje counter monotonii proti upstream

Při kolizi: push zablokován, výstup:
```
✗ ID collision detected:
  Local:    STO-79 (this branch, "Calendar widget")
  Upstream: STO-79 (origin/main, "Login flow")

To fix, run:
  python3 .claude/edpa/scripts/renumber_collisions.py
```

Pokrývá cross-branch race **před** push — žádné špinavé PRs.

### Vrstva 7 (resolution): `renumber_collisions.py` helper

Po detekci kolize:

```
$ python3 .claude/edpa/scripts/renumber_collisions.py
Fetching upstream...
Detected collision: STO-79 exists on origin/main and in your branch.
  Local file: .edpa/backlog/story/STO-79.md (title: "Calendar widget")
  Upstream:   .edpa/backlog/story/STO-79.md (title: "Login flow")

Resolution:
  - Max upstream story ID: 81
  - Renumber local STO-79 → STO-82
  - Rename file
  - Update id: field
  - Update parent: refs in 3 other files (EPI-3, STO-77, STO-78)
  - Bump counter to 82

Apply? [y/N]: y
Done. Stage and amend last commit (or create new commit) and re-push.
```

### Souhrn: kdy která vrstva zafunguje

| Scénář | V1 | V2 | V3 | V4 | V5 | V6 | V7 |
|---|---|---|---|---|---|---|---|
| Ruční filesystem edit | ✓ | — | — | ✓ | ✓ | — | — |
| Dva MCP procesy paralelně | — | ✓ | — | — | — | — | — |
| Klient zopakuje request | — | — | ✓ | — | — | — | — |
| Stejný branch, dva devs | — | — | — | — | ✓ | ✓ | manual |
| Dva PRs paralelně | — | — | — | — | — | ✓ | semi-auto |
| Edge: smazaný counter file | ✓ | — | — | — | — | — | — |

**Žádný single point of failure. Žádná GH CI.**

### Caveat: `--no-verify` bypass

Pre-commit / pre-push hooks lze obejít `git commit --no-verify` / `git push --no-verify`. Pro EDPA cílovou skupinu (malé týmy, mutual trust) je to akceptovatelný kompromis. Pokud potřeba team-policy enforcement, alternativa:
- Self-hosted git server (Forgejo, Gitea) podporuje server-side hooks → stejná logika `validate_ids.py --pre-receive` běží na serveru, nelze obejít
- GitHub-hosted: server-side hooks nejsou dostupné, ale lze přidat soft check (poslední záchrana) — branch protection s required status check, který trigger script lokálně (GH Action by tady byla legitimní pojistka, ale nepovinná)

### Alternativní úvaha (odmítnuto pro V2.0): ULID jako stable ID

Mohli bychom mít `uid: 01HV8X3K9P` + `id: STO-79` (renumberable). Kolize na display ID = jen rename, parent refs (přes UID) intact. Ale: dvojí ID surface, schema +1 pole všude, lidé budou plést. Pro tým < 10 devs a < 100 položek/měsíc je 6-vrstvý defense levnější než permanentní ULID overhead. Pokud kolize budou opakovaný problém v V2.0 provozu, V2.x přidá UID.

## Plugin skills mapa

| Skill | Před | Po (V2.0) |
|---|---|---|
| `edpa-setup` | Provisions GH Project, fields, labels, workflows | Init `.edpa/` strukturu, vendor MCP + (optional) server, žádný GH |
| `edpa-add` | `gh issue create` → ID → YAML | Volá MCP `edpa_item_create` |
| `edpa-sync` | Bidirectional GH ↔ YAML (~1800 ř.) | **SMAZÁNO** |
| `edpa-sync-people` | Pull GH collaborators do people.yaml | **SMAZÁNO** |
| `edpa-engine` | Pulls GH PR data + git evidence | Pulls **git** PR data + commit evidence (zůstává) |
| `edpa-reports` | YAML + GH timestamps | YAML + **git-derived** timestamps |
| `edpa-board` | YAML → self-contained HTML | **BEZE ZMĚNY** (už dnes nemá GH calls) |
| `edpa-close-iteration` | Orchestrates engine + reports | **BEZE ZMĚNY** (volá nezávislé skripty) |
| `edpa-autocalib` | Monte Carlo na CW heuristics | **BEZE ZMĚNY** |
| `edpa-validate` | Schema check | **BEZE ZMĚNY** |
| `edpa-server` (NOVÉ) | — | `start` / `stop` lokálního PI planning serveru |

## Server lifecycle (V1: optional komplement)

Per rozhodnutí v concept.md: PI server **není canonical** v V2.0, je rich komplement. V1 cesta:

1. `install.sh` vendoruje `tools/pi-planning/dist/` + `server/` → `.claude/edpa/server/` (~50 MB s node_modules). Volitelný extra parametr `--with-server`, aby setup zůstal štíhlý pro headless uživatele.
2. `edpa-server` skill:
   - `start`: spawn `node .claude/edpa/server/index.js --port 3001`, PID → `.edpa/.server.pid` (gitignored)
   - `stop`: kill PID
   - `status`: PID file lookup
3. Server čte/píše přes MCP klienta (HTTP routes → MCP stdio call → JSON-RPC) — **ne přímo YAML**. To zajišťuje, že server a CLI vidí identický state přes identickou validační vrstvu.
4. Per-dev `localhost:3001`, žádný shared instance. Multi-user UX přijde s V2.x (canonical).

**V2.x (později, ne teď):** PI server se stane canonical edit UI, MCP write tools dostanou HTTP routes, CLI/skills přejdou na sekundární. Nepředjímat — počkat na adoption signál z V2.0.

## Timestamps — náhrada za GH API

`sync.py:441-460` dnes pulluje `createdAt`/`closedAt`/`updatedAt` z GH issue. Náhrady:

| Pole | Nový zdroj | Implementace |
|---|---|---|
| `created_at` | `git log --diff-filter=A --follow --format=%aI -- {path}` | First commit, kde soubor vznikl |
| `updated_at` | `git log -1 --format=%aI -- {path}` | Last commit touching soubor |
| `closed_at` | `git log -G '^status:\s*Done' --format=%aI -- {path}` | First commit, kde status flipl na Done |

Pattern už existuje v `detect_contributors.py` (git blame). Nová funkce v `_git_timestamps.py` (NEW), volaná z `edpa_item` MCP tool + `engine.py`.

## Discussion / komentáře

V V2.0: **Drop**. Discussion se přesouvá do PR review commentů nebo externí chat (Slack). EDPA item nemá vlastní thread. Engine už dnes čte PR komenty pro CW evidence, takže "co se kolem položky řeklo" jde dohledat — ale ne jako diskuzní fórum.

**Alternativa pro budoucnost (PR-linked, viz dodatek na konci):** pokud se ukáže, že drop bolí, V2.1 může přidat MCP `edpa_item_discussion(item_id)`, který vrátí review komenty z PRs zmiňujících daný item ID. Bez nového storage, leverage existing PR evidence pull.

## Critical files

**Modifikace:**
- `plugin/edpa/scripts/mcp_server.py` — přidat ~7 write tool handlerů (`@server.call_tool()` dispatcher)
- `plugin/edpa/scripts/backlog.py` — `cmd_add` přestane volat `_gh_issue_factory`, volá `id_counter.next()` + zapíše YAML přímo
- `plugin/edpa/scripts/project_setup.py` — osekat z ~1050 na ~150 ř., zachovat jen init `.edpa/` struktury
- `plugin/edpa/scripts/engine.py` — timestamps via `_git_timestamps.py` místo GH metadat
- `plugin/edpa/scripts/detect_contributors.py` — **refactor na gh-optional** (viz [verification.md § Finding 7.1](./verification.md#finding-71-detect_contributorspy-do-critical-files--modifikace)): `if gh_authenticated() and config.evidence.use_gh: full pipeline else: git_only_fallback()` + stderr warning. V git-only fallbacku zachovat `commit_author`, `manual:commit_message`, delegovat na `yaml_edit_signals.py` a `transitions.py`. **CRITICAL**: bez tohoto refactoru engine v V2 bez `gh auth` crashne nebo produkuje degradované cw bez warningu.
- `plugin/edpa/scripts/autocalibrate.py` — detekuje mode (`gh_authenticated()`), v "no-gh" profilu vynechá zkoumání GH-only signal weights (viz [verification.md § Finding 7.3](./verification.md#finding-73-autocalib-mode-detection))
- `plugin/edpa/scripts/_md_frontmatter.py` — beze změny (už dnes generic)
- `plugin/skills/edpa-setup/SKILL.md` — vystřihnout GH provisioning sekce, přidat `evidence:` blok do default `edpa.yaml`
- `plugin/skills/edpa-add/SKILL.md` — přepsat na "MCP-first, local counter"

**Nové:**
- `plugin/edpa/scripts/id_counter.py` — atomic counter s `max(counters, fs_scan)` resolution + file lock
- `plugin/edpa/scripts/_git_timestamps.py` — timestamps z git logu
- `plugin/edpa/scripts/validate_ids.py` — sdílená validace pro pre-commit + pre-push (`--staged`, `--pre-push`)
- `plugin/edpa/scripts/renumber_collisions.py` — semi-auto resolution kolizí
- `plugin/edpa/scripts/migrate_v1_to_v2.py` — viz Migrace níže
- `plugin/edpa/hooks/pre-commit` — shell wrapper, instalován symlinkem do `.git/hooks/`
- `plugin/edpa/hooks/pre-push` — shell wrapper, instalován symlinkem do `.git/hooks/`
- `plugin/skills/edpa-server/SKILL.md` + `plugin/commands/server.md` — start/stop PI server

**Smazat:**
- `plugin/edpa/scripts/sync.py` (~1800 ř.)
- `plugin/edpa/scripts/_gh_issue_factory.py`
- `plugin/edpa/scripts/_sub_issue_linker.py`
- `plugin/edpa/scripts/sync_collaborators.py`
- `plugin/edpa/scripts/project_views.py` (pokud existuje)
- `plugin/skills/edpa-sync/`
- `plugin/skills/edpa-sync-people/`

**Testy:**
- `tests/test_mcp_server.py` — rozšířit o write tool testy (idempotence, validace, atomicita ID counteru)
- `tests/test_id_counter.py` (NEW) — concurrent increment, fs_scan fallback, file lock, simulace race
- `tests/test_validate_ids.py` (NEW) — pre-commit + pre-push scénáře (staged duplicit, upstream collision, counter monotonie)
- `tests/test_renumber_collisions.py` (NEW) — auto-resolution s parent: ref propagation
- `tests/test_git_timestamps.py` (NEW) — created/updated/closed extraction z fixture repos
- `tests/test_migrate_v1_to_v2.py` (NEW) — round-trip migrace na sandbox repu

## Release strategie

**Hard cut v 2.0** s V1 zálohou:

1. **Tag a větev V1**: `git tag v1.23.x-final` na současný main, vytvořit dlouhodobou větev `v1-github-coupled` jako záloha pro existující GH-coupled uživatele
2. **main = V2 vývoj**: na main začít V2.0 práci v sekvenci:
   - Krok 1: Přidat MCP write tools (bez odstranění čehokoliv) — testy zajistí, že fungují
   - Krok 2: Refactor `edpa-add` skill na MCP write tools (`backlog.py` stále má GH cesty, dual mode)
   - Krok 3: Implementovat `id_counter.py` (s file lockem) + `_git_timestamps.py`
   - Krok 4: Implementovat `validate_ids.py` + `renumber_collisions.py` + git hooks; `install.sh` instaluje hooks symlinkem do `.git/hooks/`
   - Krok 4.5: Refactor `detect_contributors.py` na gh-optional (graceful fallback, stderr warning) + `evidence.use_gh` v `edpa.yaml` schema (viz Decisions Q3). **Prerequisite k testování engine v no-gh režimu.**
   - Krok 5: Migration skript (viz níže) + E2E test na sandboxu
   - **Gate 5→6:** Migration MUSÍ projít na sandboxu + minimálně 1 reálném projektu před krokem 6 (viz [verification.md § Finding 7.5](./verification.md#finding-75-migration-test-prerequisite)). Pokud migrace neprojde, zastavit V2.0 release a opravit.
   - Krok 6: Smazat GH kód (`sync.py`, `_gh_*`, skills) — **breaking change**
   - Krok 7: `edpa-server` skill (volitelné s `--with-server` flagem)
   - Krok 8: Release V2.0 + CHANGELOG s migration steps
3. **Dokumentace**:
   - `docs/v2-to-v2-migration.md` — krok-za-krokem (nahrazuje dnešní stručný `docs/migration-v2.md`)
   - `v1-github-coupled` větev má vlastní README s "use this if you need GH integration"

## Migration skript (`migrate_v1_to_v2.py`)

Pro existující GH-coupled projekt:

1. **Pull final state** z GH: `edpa-sync pull --commit` (poslední běh sync.py před smazáním)
2. **Scan backlog**: najít `max(issue_number)` per type → seed `id_counters.yaml`
3. **Backfill timestamps**: pro každý item, jehož YAML nemá `created_at`/`closed_at`, vyplnit z git logu (přes `_git_timestamps.py`)
4. **Archive sync state**: přesunout `.edpa/config/issue_map.yaml` → `.edpa/archive/issue_map_v1.yaml` (pro pozdější dohledání starých issue numbers)
5. **Strip edpa.yaml**: odstranit `sync:` blok (github_org, github_project_number, field_ids, option_ids)
6. **Commit**: jeden "v1→v2 migration" commit
7. **Print**: instruction, jak archivovat GH Project (nedeletovat, jen unlink) pro historický audit

## Verification

Po implementaci ověřit:

1. **Žádné `gh` v sync / ID / project board / setup paths**:
   `rg -n '\bgh\s' plugin/edpa/scripts/{backlog,project_setup,mcp_server,id_counter}.py` vrátí 0 hits.
   Engine evidence (`engine.py`) smí `gh` volat optionally (viz Decisions § Q3) — s graceful fallback.
2. **MCP write roundtrip**:
   ```bash
   edpa_item_create type=story title="Test" → ID
   edpa_item_update item_id=STO-X status=InProgress
   edpa_item_transition item_id=STO-X status=Done
   cat .edpa/backlog/story/STO-X.md   # closed_at populated, status=Done
   ```
3. **Idempotence**: dvojí `edpa_item_create` se stejným `idempotency_key` vrátí stejné ID, ne nové
4. **Counter atomicita pod lockem**: spustit 2 paralelní `edpa_item_create` (přes `python3 -c "..." &` na stejném repu) → výsledné 2 různé ID, žádná kolize na disku
5. **Pre-commit hook**:
   - Ručně vytvořit kolidující `.edpa/backlog/story/STO-79.md` (kde STO-79 už existuje) → `git commit` zablokován
   - Vytvořit nový soubor s mismatch filename ≠ frontmatter id → `git commit` zablokován
6. **Pre-push hook**:
   - Branch A vytvoří STO-79, pushne. Branch B (vytvořený před A) také vytvoří STO-79, zkusí push → blokováno s návrhem `renumber_collisions.py`
7. **`renumber_collisions.py` end-to-end**: simulovat kolizi → spustit helper → ověřit, že ID, filename, counter, a parent: refs ve všech ostatních souborech jsou updateované
8. **End-to-end iteration close**: `edpa-close-iteration` projde od backlog read → engine compute → reports gen. Engine smí selektivně volat `gh` pro PR evidence, ale rest musí fungovat i bez `gh auth`
9. **Board render**: `python3 .claude/edpa/scripts/board.py` produkuje HTML beze změny vs. dnes
10. **PI server roundtrip** (pokud zapnuto): `edpa-server start` → `curl localhost:3001/api/backlog` vrátí JSON identický s `mcp_server` výstupem
11. **Migration na sandbox**: spustit `migrate_v1_to_v2.py` na E2E sandbox repu, ověřit, že timestamps sedí, counter je správně seedovaný, hooks instalované
12. **Test suite**: `pytest tests/` — všechny green, vč. nových `test_id_counter.py`, `test_validate_ids.py`, `test_renumber_collisions.py`, `test_git_timestamps.py`, `test_migrate_v1_to_v2.py`
13. **No-gh fallback E2E** (viz [verification.md § Finding 7.4](./verification.md#finding-74-verification-section-v-planmd--chybí-no-gh-test)): na sandbox repu odhlásit `gh auth logout`, spustit `edpa-close-iteration` → engine produkuje cw bez crashe, warning na stderr, contributors[] obsahuje jen git-native signal typy (commit_author, manual:commit_message, yaml_edit:*, gate_events). Resulting reports mají flag `evidence: git-only`. Cross-check, že workflow s `gh auth login` zpět produkuje **stejné** cw jako před logout (tj. fallback je deterministický bypass, ne destruktivní change).

## Co se ztrácí (vědomě)

- GH Issues UI (browse, mention, link)
- GH Project board (drag-drop UI)
- GH notifications (issue mentions, assignments → email)
- Cross-repo issue refs (`org/other-repo#42`)
- Native sub-issues (parent/child už máme v YAML, ale bez GH UI render)
- 3rd-party integrace (Slack-GH bridge, Linear sync, …)
- Inline discussion threads

## Co se získává

- Offline-first (let, vlak, výpadek GH)
- Žádný `gh auth` setup pro nové collaboratory
- ~500× rychlejší `next_id` (bez API roundtrip)
- ~30 % redukce kódu (`sync.py` complexity + drift bugs eliminované)
- Deterministické testy (žádný GH mock)
- Portable (GitLab, Forgejo, Gitea → fungují identicky)
- Jednodušší DR (žádné issue numbers v GH → restore z YAML nevyžaduje renumber)
- Plugin-based deploy (EDPA plugin = celý systém, nic dalšího nepotřeba)

---

## Dodatek: PR-linked discussion (pro V2.1+ úvahu)

Pokud po V2.0 vyhodnotíme, že "drop discussion" bolí, varianta **bez nového storage**:

**Mechanika:**
- Engine už dnes pulluje PR review komenty pro CW evidence (`engine.py` — `pr_review_comments`)
- Přidat MCP tool `edpa_item_discussion(item_id) → list[Comment]`, který:
  1. Najde PRs zmiňující `item_id` (přes title regex nebo "Closes STO-42" v body)
  2. Vrátí review + issue komenty z těch PRs jako structured list (`{author, timestamp, body, pr_url}`)
- Board/PI UI je zobrazí jako "Discussion" sekci

**Plus:**
- Žádné nové storage
- Žádná migrace dat
- Discussion má kontext (jaký PR, jaká část kódu)

**Mínus:**
- Discussion existuje **jen pro items s PR** — open epic bez práce nemá kam diskutovat
- Edge case: PR linkuje více items → komenty se duplikují
- Závisí na konvenci, že PRs zmiňují item ID v title/body (dnes EDPA tlačí přes `edpa-add` flow, takže standardní praxe)
- Pokud ztratíš GH (DR scénář), ztrácíš i discussion (na rozdíl od YAML storage)

**Doporučení:** V2.0 jít s **Drop**. Posbírat 3-6 měsíců signálu. Pokud "kde to bylo řečeno" je opakovaný request, V2.1 přidat PR-linked jako čistý read-only feature. Embed do YAML nedělat — vytváří mergesnímatelný state, který se chová jako mini-sync (přesně to, čeho se chceme zbavit).

## Decisions (resolved open questions)

### Q1: `--with-server` flag default v `install.sh`

**Rozhodnutí:** Default **OFF**, viditelný hint během install.

```
$ ./install.sh
EDPA v2.0.0 installed (~5 MB).
Hooks instalovány: pre-commit, pre-push.

Optional: Add PI planning UI server (~50 MB, requires Node.js):
  ./install.sh --with-server
```

Proč: V2.0 explicitně říká, že PI tool je komplement, ne canonical. Většina Claude Code uživatelů nepotřebuje Node server. Snadný re-install s flagem. V2.x (kdy bude canonical) překlopit na default ON.

### Q2: `github:` pole v `people.yaml`

**Rozhodnutí:** **ZACHOVAT**, schema-mark jako optional.

```yaml
- id: jurby
  name: Jaroslav Urbánek
  role: lead
  fte: 1.0
  github: jurby           # optional — pro engine PR evidence + budoucí integrace
```

Proč: engine evidence z PR (viz Q3) potřebuje mapping GH author → person. Náklad zachování = 1 optional field. Deprecation by byla symbolická, ne praktická. Pro projekty bez `gh` zůstává prázdné.

### Q3: Engine evidence z `gh` — fully local nebo optional dependency?

**Rozhodnutí:** **Optional `gh` dependency s graceful fallback.** Jazyk "žádný `gh`" upřesněn na scope sync/ID/board/setup.

**Schema v `edpa.yaml`** (V2 přidává):
```yaml
evidence:
  use_gh: true            # auto-detect z gh auth; override na false pro forced git-only
  warn_on_fallback: true  # emit stderr warning, když gh chybí a fallback aktivován
```

Default `use_gh: true` — většina uživatelů má `gh auth` setup. CI / no-auth scénáře mohou nastavit `false`.

**Pipeline v `detect_contributors.py`** (viz Critical files):
```python
def collect_signals(repo, item_id):
    if gh_authenticated() and config.evidence.use_gh:
        return full_pipeline_with_gh(repo, item_id)
    if config.evidence.warn_on_fallback:
        sys.stderr.write("⚠️  Reduced signal — gh not available, falling back to git-only evidence\n")
    return git_only_fallback(repo, item_id)
```

**Závazný jazyk pro celý plán a docs:**

> ❌ ~~"Žádný `gh` v EDPA scriptech."~~
> ✅ **"Žádný `gh` v sync / ID / project board / setup. Engine evidence smí `gh` použít jako optional read-only enhancement; fallback na čistě git data, pokud `gh` chybí."**

Klíčový rozdíl: `gh` pro **identitu a coupling** = pryč (to byl problém). `gh` pro **read-only enrichment** = optional (užitečné, neničí offline-first promise).

**Důležité:** Pro tým s formálním PR review workflow je `gh auth` **strongly recommended** — bez něj se ztratí ~50-60 % signal kvality pro review-heavy roles (viz [verification.md § 4.2](./verification.md#42-v2-bez-gh-offline--no-auth)). V2 "offline" znamená "runs", ne "runs equally well".

## Open questions (zbývající)

- **Server↔MCP transport**: PI server čte/píše přes MCP — jak? Tři varianty:
  - (a) Spawn MCP subprocess per HTTP request (drahé, jednoduché)
  - (b) Drží jeden long-lived MCP subprocess (komplikovanější lifecycle, ale efektivní)
  - (c) Importuje MCP handler funkce přímo do Node procesu přes Python embedding (porušuje vrstvení)
  Návrh: **(b)** — long-lived subprocess, restart on crash. Detail v V2.0 implementaci.
- **Multi-user koordinace v týmu**: každý dev běží lokální server → vidí jen svůj git state. PM uvidí "co se plánuje teď" přes `git pull && edpa-server start`. Žádné shared server v V2.0. Explicitně pojmenovat v dokumentaci, aby týmy nezačaly hledat sdílenou instanci.

## Reference

- **Concept overview:** [concept.md](./concept.md)
- **Architecture Decision Records:** [decisions.md](./decisions.md) — proč jsme zvolili, co jsme zvolili (11 ADRs)
- **Stávající MCP server docs:** [../mcp.md](../mcp.md)
- **Předchozí migration doc (V1.x):** [../migration-v2.md](../migration-v2.md) (zachovat jako historický odkaz)
- **PI planning tool:** `tools/pi-planning/`
- **Plugin marketplace:** `.claude-plugin/marketplace.json`
