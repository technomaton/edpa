<!-- Canonical source. Web mirror at web/src/pages/docs/edpa-token-setup.md
     uses the same body — keep both in sync when editing. -->

# EDPA_TOKEN — průvodce nastavením

> **Komu je určeno:** každý, kdo nasadil EDPA na repo a chce, aby
> **contribution-sync workflow** (`edpa-contribution-sync.yml`) běžel
> po merge PR automaticky — tedy aby se PR-thread signály
> (`pr_reviewer`, `issue_comment`) materializovaly zpět do
> `evidence[]` položky v `.edpa/backlog/**/*.md` bez manuální obsluhy.
>
> **Čas:** ~5 minut. **Frekvence:** jednou per repo (nebo jednou per
> org pokud použiješ organization secret).
>
> **Kdy to vůbec potřebuješ:** jen pokud tým má signály, které
> nežijí v git historii — reviews a komentáře v PR/issue threadech.
> Primární atribuce v V2.1+ jde přes lokální post-commit hook
> (`local_evidence.py`), který emituje `commit_author` offline a
> žádný token nepotřebuje. Single-dev / review-light / mimo-GitHub
> týmy tenhle workflow (a tím i `EDPA_TOKEN`) vynechají.

## 1. Proč to potřebuješ

Po merge PR, který referencuje EDPA položku, naskočí workflow
`edpa-contribution-sync.yml`. Ten spustí
`.edpa/engine/scripts/sync_pr_contributions.py`, který přečte review
a komentáře z PR threadu a zapíše je jako `evidence[]` záznamy do
příslušného `.edpa/backlog/**/*.md` (commit zpět na base branch).

Default `GITHUB_TOKEN`, který GitHub injektuje do každého runu, je
pro tenhle scénář často nedostatečný — typicky když PR přichází
z forku, nebo když má org restrikce na default-token write/push.
V takovém případě má job přiznané `contents: write`, ale push se
přesto odrazí. Robustní řešení je dát workflowu vlastní token.

Řešení: **Personal Access Token (PAT)** se správnými permissions,
uložený jako repo nebo org secret pod jménem `EDPA_TOKEN`.

## 2. Klasický PAT vs. Fine-grained PAT

| | Fine-grained (preferred) | Classic |
|---|---|---|
| Scope granularita | per-repo, časově omezené, vybrané permissions | celý účet, široké scopes |
| Expirace | povinná (max 1 rok) | volitelná |
| Audit log | kompletní per-action | hrubý |
| Doporučení | **default pro produkční pilots** | jen pokud fine-grained něco neumožňuje |

**Tento průvodce používá fine-grained PAT.** Pokud máš důvod pro
classic, na konci je sekce s odlišnostmi.

## 3. Vytvoření PAT (fine-grained)

1. Přihlas se do GitHubu jako **vlastník repa nebo člen org s write
   přístupem k repu** (typicky pilot lead).

2. **Settings** (avatar vpravo nahoře → Settings) → vlevo dole
   **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
   Přímý odkaz: <https://github.com/settings/personal-access-tokens/new>

3. Vyplň formulář:

   | Pole | Hodnota |
   |---|---|
   | **Token name** | `EDPA contribution-sync — <org>/<repo>` (např. `EDPA contribution-sync — kashealth/kas-platform-v1`) |
   | **Expiration** | `1 year` (rotuj kalendářně, viz §6) |
   | **Description** | "Used by .github/workflows/edpa-contribution-sync.yml to materialize PR-thread signals into .edpa/backlog evidence[]." |
   | **Resource owner** | Vyber **org** (např. `kashealth`) nebo vlastníka repa — token musí mít přístup k repu, kde EDPA poběží |
   | **Repository access** | `Only select repositories` → vyber `kas-platform-v1` (a další repos kde EDPA poběží) |

4. **Permissions** (důležitá část):

   **Repository permissions** (pro tu jednu vybranou repo):
   - **Contents**: `Read and write` ← **critical** — workflow commituje
     materializaci `evidence[]` zpět do `.edpa/backlog/**/*.md` na base branch
   - **Pull requests**: `Read` (workflow čte reviews a komentáře z PR threadu)
   - **Metadata**: `Read-only` (automaticky, povinné)

   To je celý nutný scope. Workflow **nevytváří ani needituje Issues**
   a v V2 **neexistují žádné GitHub Project items** — žádné Projects /
   Issues / org permissions tedy nepotřebuješ.

   *(Volitelně:* pokud na repu provozuješ i `edpa-collaborators-sync.yml`,
   přidej **Organization → Members: `Read-only`** pro lookup členství.
   Pro samotný contribution-sync to není potřeba.)*

5. **Generate token** → **CRITICAL: token se ukáže JEN JEDNOU.**
   Zkopíruj `ghp_...` string do clipboardu, hned přejdi na krok 4.
   Pokud zavřeš tab bez zkopírování, musíš vygenerovat nový.

## 4. Uložení tokenu do repo secrets

1. Otevři repo: `https://github.com/<org>/<repo>`

2. **Settings** (záložka v horní liště repa) → vlevo **Secrets and
   variables** → **Actions** → **New repository secret**

3. Vyplň:
   - **Name:** `EDPA_TOKEN` (přesně, case-sensitive, žádné underscore navíc)
   - **Secret:** vlož `ghp_...` z clipboardu

4. **Add secret**. Token je teď v repo store, šifrovaný; ani majitel
   repa už nikdy neuvidí plaintext (GitHub ho re-injektuje do workflow
   runů přes maskovanou env proměnnou).

### Variant: Organization secret pro víc repos

Pokud máš v org víc repos s EDPA, je čistší uložit jeden PAT jako
**organization secret** a sdílet ho:

1. `https://github.com/<org>` → **Settings** → **Secrets and
   variables** → **Actions** → **New organization secret**
2. **Name:** `EDPA_TOKEN`, **Secret:** PAT value
3. **Repository access:** `Selected repositories` → vyber všechna
   repos, kde EDPA workflow běží
4. **Add secret**

Bonus: rotation pak děláš jen jednou per org místo per-repo.

## 5. Verifikace

Workflow je **merge-triggered** — naskočí, až se mergne PR, který
referencuje EDPA položku (ID v názvu/popisu PR nebo v commitu).
Otestuj ho tedy přes malý PR, ne přímým pushem do base branche:

```bash
cd ~/projects/<repo>
git checkout -b test/edpa-sync
# udělej drobnou změnu a odkaž EDPA položku (např. F-1) v commitu
git commit -am "test: trigger EDPA contribution sync (F-1)"
git push -u origin test/edpa-sync
gh pr create --fill        # přidej review/komentář, ať je co materializovat
gh pr merge --squash       # merge spustí workflow
```

Pak otevři `https://github.com/<org>/<repo>/actions` a sleduj:

| Workflow | Očekávaný stav |
|---|---|
| `EDPA contribution sync` | ✓ Success (běží po merge PR, `if merged == true`) |

Po doběhnutí (cca 20-40 s) vznikne commit od `edpa-bot` na base
branchi, který do `.edpa/backlog/<type>/<id>.md` doplní `evidence[]`
záznamy (`pr_reviewer` / `issue_comment`). Lokálně si to stáhneš
přes `git pull` — a tyhle obohacené signály pak započítá nejbližší
`/edpa:close-iteration` (engine čte YAML frontmatter položky).

### Co když to nefunguje

| Symptom | Příčina | Fix |
|---|---|---|
| `::warning::EDPA_TOKEN secret not configured` v logu | Secret se jmenuje špatně | Přejmenuj na přesně `EDPA_TOKEN` |
| Workflow naskočí, ale push na base branch selže (`403`/`protected branch`) | Token nemá `Contents: write`, nebo branch protection blokuje push | Edit token → Contents: Read and write; případně povol pushe od bota přes branch protection |
| `Failed to push after 3 retries` v logu | Souběžný commit na base branch / race | Re-run workflow; rebase-retry si většinou poradí sám |
| Workflow naběhl, commit vznikl, ale `evidence[]` prázdné | PR nemá review ani komentář, nebo neodkazuje EDPA ID | Přidej review/komentář; ujisti se, že PR/commit odkazuje existující item ID |
| `Please tell me who you are` při git commit | Workflow nemá git config step (legacy verze) | Updatuj `edpa-contribution-sync.yml` na aktuální template |

## 6. Rotace tokenu

Fine-grained PATs mají povinnou expiraci (max 1 rok). Bez rotace
workflow začne fail-ovat v den expirace.

**Doporučená cadence:**

1. Den vytvoření zapiš do týmového kalendáře jako recurring event
   "Rotate EDPA_TOKEN" s reminderem **2 týdny před expirací**.
2. Den rotace:
   - Generate new token (stejné permissions, nové expirační datum)
   - Update secret value v *Settings → Secrets → EDPA_TOKEN*
   - Stary token: **Settings → Personal access tokens → Revoke**
   - Push test commit → ověř Actions tab → ✓

**Tip:** GitHub posílá expirační warning email 7 dní před vypršením.
Nech si filtr na ten subject, ať ti to nezapadne ve spamu.

## 7. Pokud token nemůžeš nastavit (co přijdeš o)

`EDPA_TOKEN` je v V2 čistě volitelný. Když ho nenastavíš (nebo ti
vyprší mezi rotacemi), **nepřijdeš o jádro atribuce** — to běží lokálně:

- Post-commit hook `local_evidence.py` emituje `commit_author` pro
  každý commit, který odkazuje EDPA položku. Funguje offline, bez
  GitHubu, bez tokenu.
- `/edpa:close-iteration` běží **lokálně** a žádný token nepotřebuje.

Co bez tokenu (resp. bez contribution-sync workflowu) nedostaneš:
- **PR-thread signály** `pr_reviewer` a `issue_comment` se
  automaticky nematerializují do `evidence[]`. Reviews a komentáře
  z PR threadů tedy nebudou ve výpočtu zohledněny.

**Doporučení:** pokud je tým single-dev nebo review-light, klidně
workflow i token vynechej — lokální hook stačí. Jakmile začnou
záležet code-review signály, nastav `EDPA_TOKEN` a zapni workflow.

## 8. Classic PAT (legacy varianta)

Pokud z nějakého důvodu fine-grained nemůžeš použít (např. org policy
restrikce, fine-grained nevyřízené org approval requests), klasický PAT
funguje taky:

1. *Settings → Developer settings → Personal access tokens → Tokens
   (classic) → Generate new token (classic)*
2. **Scopes:** zaškrtni:
   - `repo` (full control of private repositories — pokrývá Contents
     write i Pull requests read, které workflow potřebuje)
3. Generate token → ulož do `EDPA_TOKEN` secret stejně jako v §4

**Rozdíly proti fine-grained:**
- ⚠️ Mnohem širší scope (token vidí všechny tvé repos)
- ⚠️ Žádná povinná expirace (lehce zapomeneš na rotaci → security drift)
- Bez audit logu per action

Pokud máš na výběr, vždy preferuj fine-grained.

## 9. FAQ

**Q: Token v secretu vidí kdokoli s admin přístupem k repu?**
A: Ne. Po uložení je hodnota nečitelná i pro repo ownery. Vidí se jen
že existuje. Plaintext zná jen ten kdo ho vytvořil a měl ho v clipboardu.

**Q: Co když token leakne (commit, screenshot, …)?**
A: Hned ho revoke v *Settings → PATs → Revoke*. Vygeneruj nový, updatuj
secret. Bývalý token přestane fungovat během sekund.

**Q: Můžu použít GitHub App místo PAT?**
A: Ano, ale je to víc setupu. Pro pilot fázi je PAT pragmatičtější.
Až EDPA poběží na 10+ repos, refaktoring na GitHub App dává smysl —
ozvi se a probereme.

**Q: Co se stane když token expiruje uprostřed PI close?**
A: Na PI close to nemá vliv. `/edpa:close-iteration` běží **lokálně**
a token nikdy nepotřebuje — token používá jen post-merge
contribution-sync workflow. Expirovaný token tedy jen znamená, že se
do nejbližšího close nepřilijí čerstvé `pr_reviewer`/`issue_comment`
signály z PR threadů. Rotuj token (viz §6) a po zapnutí workflowu se
dorovnají při dalších merge.

---

**Související dokumenty:**
- [`docs/kashealth-pilot/KASHEALTH-PILOT.md`](kashealth-pilot/KASHEALTH-PILOT.md) — pilot runbook
- [`plugin/edpa/templates/github-workflows/edpa-contribution-sync.yml`](../plugin/edpa/templates/github-workflows/edpa-contribution-sync.yml) — merge-triggered contribution sync (PR-thread signály → `evidence[]`)
- [`plugin/edpa/scripts/sync_pr_contributions.py`](../plugin/edpa/scripts/sync_pr_contributions.py) — skript, který workflow spouští

---

*Verze dokumentu: 2.1.8 · 2026-05-31*
