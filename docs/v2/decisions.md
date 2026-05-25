# EDPA V2 — Architecture Decision Records

> **Status:** Všechna rozhodnutí ve stavu **Accepted (pending V2.0 implementation)**.
> **Hlavní dokumenty:** [concept.md](./concept.md), [plan.md](./plan.md)

Tento dokument je ADR-style log (Architecture Decision Records) pro V2 transici. Každý záznam zachycuje **co**, **proč**, **jaké alternativy zvažovány** a **jaké důsledky**. Slouží jako audit trail pro budoucnost — kdyby se za rok někdo ptal "proč jsme to udělali takhle", odpověď je tady.

| # | Rozhodnutí | Status |
|---|---|---|
| [ADR-001](#adr-001-disconnect-edpa-from-github-syncidboard) | Disconnect EDPA from GitHub (sync/ID/board) | Accepted |
| [ADR-002](#adr-002-mcp-server-as-single-api-layer-over-yaml) | MCP server jako jediná API vrstva nad YAML | Accepted |
| [ADR-003](#adr-003-mcp-only-when-it-makes-sense) | "MCP jen když dává smysl" — direct script pro compute | Accepted |
| [ADR-004](#adr-004-local-sequential-id-counter) | Lokální sekvenční ID counter (vs. ULID) | Accepted |
| [ADR-005](#adr-005-local-hook-based-id-safety) | Lokální hook-based ID safety (vs. CI-based) | Accepted |
| [ADR-006](#adr-006-pi-planning-tool-as-optional-komplement-v-v20) | PI planning tool jako optional komplement v V2.0 | Accepted |
| [ADR-007](#adr-007-drop-discussion-threads-in-v20) | Drop discussion threads v V2.0 | Accepted |
| [ADR-008](#adr-008-hard-cut-release-v-v20) | Hard cut release v V2.0 (vs. deprecation cycle) | Accepted |
| [ADR-009](#adr-009-with-server-flag-default-off) | `--with-server` flag default OFF | Accepted |
| [ADR-010](#adr-010-keep-github-field-in-peopleyaml) | Zachovat `github:` field v `people.yaml` (optional) | Accepted |
| [ADR-011](#adr-011-engine-evidence-via-optional-gh) | Engine evidence via optional `gh` s graceful fallback | Accepted |

---

## ADR-001: Disconnect EDPA from GitHub (sync/ID/board)

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
EDPA je dnes silně GH-coupled: ID schéma odvozeno z `gh issue.number`, GH Project drží custom fields (Status/Iteration/Score), `sync.py` (~1800 ř.) řeší bidirectional sync. Problémy:
- Ztráta repa = ztráta identity backlog položek (čísla nepřenositelná, GH nedovolí force-set)
- Každý collaborator musí mít `gh auth` → frikce pro nové členy + offline práce nemožná
- GH outage = EDPA outage
- ~30 % komplexity v `sync.py` řeší drift, který existuje jen kvůli sync architektury samé

### Decision
EDPA V2 **kompletně odpojí** sync / ID generation / project board / setup od GitHubu. `gh` se nesmí volat z těchto cest. **Source of truth = git + YAML.**

Výjimka: engine evidence pull smí volat `gh` optionally (viz [ADR-011](#adr-011)).

### Alternatives considered
- **Status quo + backup dump** ([rejected]) — řeší jen DR, neřeší auth coupling a sync drift
- **Stable internal UID + GH issue # jako ref** ([deferred]) — clean architectural fix, ale velký refactor; zvážit pro V3
- **Split repo (tracker-only)** ([rejected]) — sníží blast radius, ale nezruší závislost
- **Dual mode dlouhodobě (`mode: github` vs `mode: local`)** ([rejected]) — víc kódu k údržbě, signalizuje nerozhodnost

### Consequences

**Pozitivní:**
- Offline-first (let, vlak, výpadek GH)
- Žádný `gh auth` setup pro nové collaboratory
- Portable (GitLab, Forgejo, Gitea fungují identicky)
- DR triviální (data jsou v gitu, žádný renumber)
- ~30 % redukce kódu

**Negativní (vědomě akceptováno):**
- Ztráta GH Issues UI, Project board, notifications, cross-repo refs
- Ztráta 3rd-party integrací (Slack-GH bridge, Linear sync)
- Inline discussion threads (řešeno [ADR-007](#adr-007))

**Související:** [ADR-002](#adr-002), [ADR-004](#adr-004), [ADR-008](#adr-008), [ADR-011](#adr-011)

---

## ADR-002: MCP server jako jediná API vrstva nad YAML

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Po odpojení od GH ([ADR-001](#adr-001)) potřebujeme jasný kontrakt mezi daty (YAML) a konzumenty (skills, CLI, lokální HTTP UI). Bez jediného API endpointu by každý konzument re-implementoval YAML parsing + validaci + write logic, což vede k drift a duplicit.

### Decision
**MCP server (`plugin/edpa/scripts/mcp_server.py`) je jediná vrstva, která čte a píše do `.edpa/`.** Skills, CLI commands i PI planning server konzumují MCP přes stdio JSON-RPC. Read tools už 8 existují (dnes všechny read-only); přidáme ~7 write tools (item create/update/transition/link, iteration create/close, people upsert).

### Alternatives considered
- **Skills volají Python scripts přímo** ([rejected]) — současný stav, vede k drift mezi skill validací a sync validací
- **Shared library importovaná všemi konzumenty** ([rejected]) — porušuje vrstvení, lokální import-only nefunguje pro Node PI server
- **HTTP REST API místo MCP** ([rejected]) — MCP už existuje a integruje se s Claude Code; HTTP by byl extra protokol

### Consequences

**Pozitivní:**
- Single source of validation logic
- Skills jsou tenké LLM wrappery, nemusí znát YAML schema
- PI server a CLI vidí identický state přes stejnou cestu
- Idempotency, locking, audit trail na jednom místě

**Negativní:**
- MCP overhead pro malé operace (zanedbatelný — stdio JSON-RPC ~10ms)
- Krátký latency penalty oproti přímému Python importu (řešeno [ADR-003](#adr-003) výjimkami pro heavy compute)

**Související:** [ADR-003](#adr-003), [ADR-005](#adr-005)

---

## ADR-003: "MCP jen když dává smysl"

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
ADR-002 říká "MCP je jediná read/write vrstva". V doslovném výkladu by to znamenalo, že engine výpočet (sekundy compute, generuje JSON soubor) a board HTML render (statický HTML soubor) musí jít přes MCP. To přidává overhead bez přidané hodnoty.

### Decision
Formalizovat **dvě kategorie operací**:
- **CRUD-shaped** (create item, update field, transition status, link parent, …) → **přes MCP**
- **Heavy compute / file generation** (engine, board render, reports, validate) → **přímo skript**

Pravidlo: MCP pro **strukturované jednotky dat** (item, iteration, person). Skript pro **batch compute** a **filesystem write artefaktů**.

### Alternatives considered
- **Vše přes MCP** ([rejected]) — overhead bez hodnoty, MCP write tool pro generování HTML je absurdní
- **Vše přímo skripty** ([rejected]) — vrací nás k pre-V2 stavu s rozptýlenou validací
- **MCP s "long-running tool" patternem** ([rejected]) — MCP protokol není designed pro tohle; spawning subprocess z MCP tool je možné, ale zbytečné

### Consequences

**Pozitivní:**
- MCP zůstává štíhlé, rychlé pro CRUD
- Heavy compute si nepřináší overhead protokolu
- Tabulka v [plan.md § Pravidlo](./plan.md#pravidlo-kdy-přes-mcp-kdy-přímo-script) je jednoznačný guide

**Negativní:**
- Dva přístupové vzorce (přes MCP / přímo) — vývojář musí vědět, kdy co. Řešeno explicitní tabulkou v dokumentaci.

**Související:** [ADR-002](#adr-002)

---

## ADR-004: Lokální sekvenční ID counter

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Po [ADR-001](#adr-001) potřebujeme lokální mechanismus pro generování ID (`STO-42`, `EPI-3`, …) bez `gh issue.number`. Volba ovlivňuje, jak budou IDs vypadat a jak řešit kolize.

### Decision
**Lokální sekvenční counter** v `.edpa/config/id_counters.yaml`:
```yaml
counters:
  initiative: 5
  story: 78
  ...
```

Display ID zachová current schema (`STO-78` → `STO-79`). ID safety přes 6-vrstvý defense (viz [ADR-005](#adr-005)).

### Alternatives considered
- **ULID jako stable ID + sequential jako display alias**
  ```yaml
  uid: 01HV8X3K9P
  id: STO-79      # renumberable on collision
  ```
  ([deferred to V3+])
  - Plus: collision na display = jen rename, parent refs (přes UID) intact
  - Minus: dvojí ID surface, schema +1 pole všude, lidé budou plést, parent refs v YAML diff nečitelné
  - Verdikt: pro tým < 10 devs a < 100 položek/měsíc je 6-vrstvý defense levnější než permanentní UID overhead
- **Timestamp-based ID** (`STO-20260525-01`) ([rejected]) — ztrácí krátkost a sekvenční čitelnost
- **UUID** ([rejected]) — totální ztráta human-readability

### Consequences

**Pozitivní:**
- Zero UX change vs. dnes (`STO-79` zůstává `STO-79`)
- Triviálně migrovatelné z GH (max existující issue.number → seed counter)
- Žádné nové ID koncepty pro uživatele

**Negativní:**
- Race conditions možné (řešeno [ADR-005](#adr-005))
- Pokud kolize budou opakovaný problém, V2.x bude muset přidat UID retroaktivně

**Související:** [ADR-005](#adr-005)

---

## ADR-005: Lokální hook-based ID safety

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Sekvenční counter ([ADR-004](#adr-004)) bez globálního arbitra (GH) může vést ke kolizím: cross-branch race, retry, manual edits, concurrent processes. Potřebujeme defense, ale **bez návratu ke GH coupling** (např. přes GH CI workflow).

### Decision
**6-vrstvý lokální defense in depth, žádná GH dependency:**

| # | Vrstva | Kdy |
|---|---|---|
| 1 | `fs_scan` v `next_id` (`max(counter, fs_scan)`) | Write time (MCP `edpa_item_create`) |
| 2 | File lock (`.edpa/.id_counter.lock`) | Write time, concurrent processes |
| 3 | Idempotency key + 24h log | Write time, retry safety |
| 4 | Pre-save validation v MCP tool | Před zápisem do YAML |
| 5 | Pre-commit hook → `validate_ids.py --staged` | Před git commit |
| 6 | Pre-push hook → `validate_ids.py --pre-push` | Před git push |

`renumber_collisions.py` jako semi-auto resolution po detekci.

### Alternatives considered
- **GH CI workflow** (`.github/workflows/edpa-validate-ids.yml`) ([rejected]) — zpětná coupling do GH, kterou se snažíme odstranit. Také pomalejší feedback (CI roundtrip).
- **Server-side git hooks na shared remote** ([deferred]) — možnost pro Forgejo/Gitea uživatele, ale ne universal. Doporučeno jako optional enhancement.
- **GH branch protection s required status check** ([deferred]) — pojistka pro GH-hostované repa, ne povinná
- **Stable ULID místo defense** (viz [ADR-004](#adr-004) alternatives) — odsunuto

### Consequences

**Pozitivní:**
- Žádný single point of failure (každá vrstva pokrývá jiný scénář)
- Žádná GH dependency — funguje na GitLab, Forgejo, Gitea, self-hosted
- Rychlejší feedback (pre-commit / pre-push lokální, ne CI roundtrip)
- Hooks instalované přes `install.sh` (symlink do `.git/hooks/`)

**Negativní:**
- `git commit --no-verify` / `git push --no-verify` lze bypass. Pro EDPA cílovku (malé týmy, mutual trust) akceptovatelné. Pro team-policy enforcement → self-hosted server-side hooks.
- Manuální resolution kolize vyžaduje znalost `renumber_collisions.py` (mitigated: vystupuje s clear hint)

**Související:** [ADR-001](#adr-001), [ADR-004](#adr-004)

---

## ADR-006: PI planning tool jako optional komplement v V2.0

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Existuje WIP PI planning tool (`tools/pi-planning/`, Express + React + Vite, ~50 MB s deps). Otázka: stane se canonical edit UI v V2.0, nebo zůstane optional? Tlak na canonical: bohaté UI pro PM/stakeholdery. Tlak na optional: V2.0 už má hodně změn, server přidává setup complexity (Node.js dependency).

### Decision
**V2.0 = optional komplement.** PI server lze nainstalovat přes `install.sh --with-server` (default OFF, viz [ADR-009](#adr-009)). Primary edit surface je CLI / skills přes MCP. Read snapshot je `board.html` (`board.py`).

**V2.x = canonical edit UI** (později, ne hned). Až bude V2.0 stabilní, PI server získá HTTP routes přes MCP write tools, CLI/skills přejdou na sekundární.

### Alternatives considered
- **V2.0 canonical edit UI** ([rejected]) — moc změn najednou, riskovat dvě věci současně (architecture + UI maturity)
- **V2.0 zcela bez PI serveru** ([rejected]) — opouští existující WIP investici; uživatelé, kteří chtějí UI, by neměli volbu
- **Hosted UI místo lokálního serveru** ([rejected]) — porušuje local-first vize

### Consequences

**Pozitivní:**
- V2.0 nese minimální riziko UI maturity
- Headless uživatelé (CI, CLI-only) neplatí za server, který nepoužívají
- PI server může zrát paralelně s V2.0 release

**Negativní:**
- Dual UX (CLI primary / server optional) — uživatelé musí vědět, co je co. Řešeno docs.
- Server↔MCP transport (long-lived subprocess vs. spawn-per-request) zůstává open question pro implementaci

**Související:** [ADR-009](#adr-009)

---

## ADR-007: Drop discussion threads v V2.0

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Po odpojení od GH ([ADR-001](#adr-001)) ztrácíme inline discussion threads na GH issue. Otázka: nahradit (embed do YAML, PR-linked, …) nebo drop?

### Decision
**Drop v V2.0.** Discussion se přesouvá do PR review commentů nebo externí chat (Slack). EDPA item nemá vlastní thread.

PR-linked alternativa zachycena jako V2.1+ kandidát ([dodatek v plan.md](./plan.md#dodatek-pr-linked-discussion-pro-v21-úvahu)). Embed do YAML explicitně **odmítnut** — vytváří mergesnímatelný state, který se chová jako mini-sync (přesně to, čeho se chceme zbavit).

### Alternatives considered
- **Embed do YAML body** (`## Discussion` sekce, MCP `edpa_item_comment_add`) ([rejected]) — vytváří merge konflikty, simuluje to, co `sync.py` dělal pro GH
- **PR-linked** (engine pulluje PR komenty zmiňující item ID) ([deferred to V2.1+]) — bez nového storage, leverage existing PR evidence pull. Plus: discussion má kontext (jaký PR). Minus: existuje jen pro items s PR.
- **External tool integration** (Slack thread per item) ([rejected]) — další coupling

### Consequences

**Pozitivní:**
- Nejjednodušší možná varianta
- Žádný nový storage, žádné merge konflikty
- Discussion v PR review je v kontextu kódu (lepší než issue thread bez kontextu)

**Negativní:**
- Items bez PR (open epic, future initiative) nemají kam diskutovat
- Ztráta diskuzního fóra pro non-dev stakeholdery, kteří byli zvyklí komentovat issues

**Plán mitigace:** Posbírat 3-6 měsíců signálu po V2.0. Pokud "kde to bylo řečeno" je opakovaný request, V2.1 přidat PR-linked jako čistý read-only feature.

**Související:** [ADR-001](#adr-001)

---

## ADR-008: Hard cut release v V2.0

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Existující EDPA instalace jsou GH-coupled. Migrace na V2 je breaking. Možné strategie: hard cut (jeden release breaking), deprecation cycle (1.x → 1.y opt-in → 2.0 remove), dual mode (`mode: github` vs `mode: local`).

### Decision
**Hard cut v 2.0 + V1 archivován na separate branch.**

- `git tag v1.23.x-final` na současný main
- Vytvořit dlouhodobou větev `v1-github-coupled` jako záloha pro uživatele, kteří chtějí staré chování
- main = V2 vývoj
- Migrace existujících projektů přes `migrate_v1_to_v2.py` skript

### Alternatives considered
- **Deprecation cycle (1.24 opt-in → 1.25 warn → 2.0 remove)** ([rejected]) — bezpečnější, ale rozprostřené, vyžaduje paralelní udržování dvou cest po měsíce
- **Dual mode dlouhodobě** ([rejected]) — víc kódu k údržbě, signalizuje nerozhodnost, neeliminuje sync.py complexity

### Consequences

**Pozitivní:**
- Rychlé, jeden major release
- Žádné dlouhé období dual-path maintenance
- V2.0 začíná s čistým štítem
- V1 zůstává accessible na branchi pro výjimky

**Negativní:**
- Větší skok pro existující uživatele
- Vyžaduje `migrate_v1_to_v2.py` jako prerequisite
- Riziko, že migrace nepokryje edge case → user zaseknutý mezi verzemi

**Plán mitigace:**
- V1 branch udržovaný (security patches, kritické bugs) po dobu N měsíců (TBD)
- Migration skript otestován na E2E sandbox repu + 1-2 reálných projektech před V2.0 release
- CHANGELOG s detailním migration walkthrough

**Související:** [ADR-001](#adr-001)

---

## ADR-009: `--with-server` flag default OFF

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
`install.sh` může vendorovat PI planning server (`tools/pi-planning/dist/` + node_modules, ~50 MB) do `.claude/edpa/server/`. Server vyžaduje Node.js runtime. Otázka: ON nebo OFF default?

### Decision
**Default OFF.** `install.sh` vypíše viditelný hint:
```
EDPA v2.0.0 installed (~5 MB).
Hooks instalovány: pre-commit, pre-push.

Optional: Add PI planning UI server (~50 MB, requires Node.js):
  ./install.sh --with-server
```

V V2.x (kdy PI server bude canonical, viz [ADR-006](#adr-006)) překlopit na default ON.

### Alternatives considered
- **Default ON** ([rejected]) — ~50 MB + Node.js dependency pro uživatele, kteří server nepotřebují (headless / CI / CLI-only)
- **Auto-detect (zapne, pokud Node existuje)** ([rejected]) — implicitní chování, uživatel neví, co dostal
- **Separate `edpa-server-install` skript** ([rejected]) — fragmentuje setup, zbytečně

### Consequences

**Pozitivní:**
- V2.0 setup zůstává štíhlý
- Headless uživatelé neplatí za server, který nepoužívají
- Re-install s flagem je triviální upgrade

**Negativní:**
- PM/stakeholder uživatel musí být explicitně informován o `--with-server`. Řešeno hintem během install + sekcí v `quick-start.md`.

**Související:** [ADR-006](#adr-006)

---

## ADR-010: Zachovat `github:` field v `people.yaml`

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
`people.yaml` dnes obsahuje GH login pro mapping (engine PR evidence, GH collaborator sync). Po odpojení od GH otázka: zachovat pole nebo deprecate?

### Decision
**Zachovat, schema-mark jako optional.**

```yaml
- id: jurby
  name: Jaroslav Urbánek
  role: lead
  fte: 1.0
  github: jurby           # optional — pro engine PR evidence + budoucí integrace
```

### Alternatives considered
- **Deprecate** ([rejected]) — engine PR evidence ([ADR-011](#adr-011)) potřebuje GH author → person mapping. Bez `github:` by engine ztratil signál.
- **Přesunout do separate `github_mapping.yaml`** ([rejected]) — fragmentace dat bez přínosu

### Consequences

**Pozitivní:**
- Engine PR evidence nadále funguje (mapping → person)
- Budoucí volitelné integrace (Linear, Jira mapping přes podobné pole) možné
- Náklad zachování = 1 optional field

**Negativní:**
- Symbolicky pole odkazuje na GitHub. Pro projekty bez `gh` zůstává prázdné — žádný funkční dopad.

**Související:** [ADR-011](#adr-011)

---

## ADR-011: Engine evidence via optional `gh` s graceful fallback

**Date:** 2026-05-25
**Decider:** Jaroslav Urbánek
**Status:** Accepted

### Context
Engine (`engine.py`) dnes čte PR review komenty přes `gh` jako CW evidence. Po [ADR-001](#adr-001) ("disconnect from GH") je otázka, zda toto použití `gh` také odstranit, nebo zachovat. Conflict: ADR-001 zakazuje `gh` v EDPA scriptech, ale PR komenty mají reálnou signal hodnotu pro engine.

### Decision
**Optional `gh` dependency s graceful fallback.** Zpřesnit jazyk celého V2 plánu.

```python
# engine.py
def fetch_pr_evidence(item_id, repo_root):
    if gh_authenticated() and edpa_config.get("evidence", {}).get("use_gh", True):
        return fetch_via_gh(item_id)         # PR review comments, full signal
    return fetch_via_git_only(item_id)       # commit messages, diff stats only
```

**Závazný jazyk pro celý plán:**
> ❌ ~~"Žádný `gh` v EDPA scriptech."~~
> ✅ **"Žádný `gh` v sync / ID / project board / setup. Engine evidence smí `gh` použít jako optional read-only enhancement; fallback na čistě git data, pokud `gh` chybí."**

### Alternatives considered
- **Plně odstranit `gh` z engine** ([rejected]) — ztráta signálu (PR review komenty obsahují kvalitu code review, discussion, schválení), engine evidence se zhorší
- **Always `gh` (no fallback)** ([rejected]) — porušuje offline-first promise, brání projektům bez `gh auth`
- **Migrate PR komenty do YAML** ([rejected]) — replikuje sync architekturu, kterou se snažíme odstranit

### Consequences

**Pozitivní:**
- Engine evidence si zachovává plný signál pro projekty s `gh`
- Projekty bez `gh` (solo dev, offline, jiný git host) fungují s sníženým signálem ale nezalomeny
- Offline-first promise zachována (engine pravidelně neběží na critical path)

**Negativní:**
- Jazyk "žádný `gh`" v plánu musel být zpřesněn — zvýšená nuance pro čtenáře
- Engine má dvě cesty kódu (gh / git-only), víc test scénářů

**Klíčový rozdíl:** `gh` pro **identitu a coupling** = pryč (to byl problém). `gh` pro **read-only enrichment** = optional (užitečné, neničí offline-first).

**Související:** [ADR-001](#adr-001), [ADR-010](#adr-010)

---

## Otevřené otázky (nevyřešené, čekají na implementační fázi)

Tyto nejsou ADR — jsou TODO pro implementační rozhodnutí, která neovlivňují architekturu na vysoké úrovni.

### OQ-1: Server↔MCP transport

PI server čte/píše přes MCP — jak konkrétně?
- (a) Spawn MCP subprocess per HTTP request (drahé, jednoduché)
- (b) Long-lived MCP subprocess (efektivní, komplexnější lifecycle) ← **návrh**
- (c) Importuje MCP handler funkce přímo do Node procesu (porušuje vrstvení)

Rozhodne se při implementaci PI serveru (V2.0 krok 7).

### OQ-2: Multi-user koordinace v týmu

V2.0 nemá shared server — každý dev běží lokální MCP / server, vidí jen svůj git state. PM uvidí "co se plánuje teď" přes `git pull && edpa-server start`. Žádné real-time sdílení.

**Akce:** Explicitně pojmenovat v `quick-start.md` a `RUNBOOK.md`, aby týmy nezačaly hledat sdílenou instanci. V2.x (canonical PI server) tento model může změnit.

---

## Update process

Tento dokument je **append-only audit log**. Pokud se rozhodnutí změní:

1. **Nepřepisovat starý ADR** — historie je důležitá
2. Změnit jeho `Status` na `Superseded by ADR-NNN`
3. Přidat nový ADR-NNN, který nahrazuje
4. V tabulce na začátku oba odkázat

Příklad: pokud V2.1 přidá ULID jako stable ID, ADR-004 dostane status `Superseded by ADR-012`, vznikne ADR-012 s novým rozhodnutím.

## Reference

- [concept.md](./concept.md) — executive summary
- [plan.md](./plan.md) — detailní implementační plán
- [migration-v2.md](../migration-v2.md) — historický migration doc V1.x
