---
layout: ../../layouts/DocsLayout.astro
title: "EDPA_TOKEN — průvodce nastavením"
description: "Step-by-step guide pro vygenerování GitHub PAT a uložení jako EDPA_TOKEN secret. Bez tohoto tokenu sync workflowy mezi .edpa/backlog/ a GitHub Project tiše no-opují."
---

<!-- Web mirror of docs/edpa-token-setup.md.
     Canonical source lives in the repo root docs/ folder; this file
     keeps the same body for browser-friendly rendering at
     https://edpa.technomaton.com/docs/edpa-token-setup.
     Keep both files in sync when editing. -->

# EDPA_TOKEN — průvodce nastavením

> **Komu je určeno:** každý, kdo nasadil EDPA na repo s **org-scoped
> GitHub Project v2** a chce, aby sync mezi `.edpa/backlog/*.yaml`
> a Project boardem běžel automaticky bez manuální obsluhy.
>
> **Čas:** ~5 minut. **Frekvence:** jednou per repo (nebo jednou per
> org pokud použiješ organization secret).
>
> **Doporučená cesta** — alternativa je `sync.py pull/push` manuálně
> před každým commitem, což škáluje jen na pár-osobový tým a jednu
> iteraci, ne na 6-měsíční pilot s týdenním close.

## 1. Proč to potřebuješ

Dva GitHub Actions workflowy (`edpa-sync-projects-to-git.yml` a
`edpa-sync-git-to-projects.yml`) volají Projects v2 GraphQL API. Default
`GITHUB_TOKEN`, který GitHub injektuje do každého workflow runu,
nemá scope pro Projects v2 (jsou **org-scoped**, ne repo-scoped) —
GraphQL vrátí 403 nebo prázdné výsledky.

Řešení: **Personal Access Token (PAT)** se správnými scopes,
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

1. Přihlas se do GitHubu jako **vlastník repa nebo členem org se
   project write právy** (typicky pilot lead).

2. **Settings** (avatar vpravo nahoře → Settings) → vlevo dole
   **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
   Přímý odkaz: <https://github.com/settings/personal-access-tokens/new>

3. Vyplň formulář:

   | Pole | Hodnota |
   |---|---|
   | **Token name** | `EDPA sync — <org>/<repo>` (např. `EDPA sync — kashealth/kas-platform-v1`) |
   | **Expiration** | `1 year` (rotuj kalendářně, viz §6) |
   | **Description** | "Automated sync between .edpa/backlog YAMLs and GitHub Project v2. Used by .github/workflows/sync-*.yml." |
   | **Resource owner** | Vyber **org** (např. `kashealth`), ne svůj user account — token bude moci přistupovat k org Projects |
   | **Repository access** | `Only select repositories` → vyber `kas-platform-v1` (a další repos kde EDPA poběží) |

4. **Permissions** (důležitá část):

   **Repository permissions** (pro tu jednu vybranou repo):
   - **Contents**: `Read and write` (auto-commit po `sync.py pull --commit` + git push)
   - **Issues**: `Read and write` (sync vytváří/edituje Issues navázané na Project items)
   - **Pull requests**: `Read` (engine čte PR metadata pro evidence detection)
   - **Metadata**: `Read-only` (automaticky, povinné)
   - **Workflows**: `Read and write` (pokud chceš povolit `update-template.yml` updateovat workflow soubory)

   **Organization permissions**:
   - **Projects**: `Read and write` ← **toto je critical, bez něj nic nepojede**
   - **Members**: `Read-only` (pro `sync_collaborators.py` lookup org membership)

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

Po uložení secretu udělej jeden test commit:

```bash
cd ~/projects/<repo>
echo "" >> .edpa/backlog/initiatives/I-1.yaml   # whitespace change
git add .edpa/ && git commit -m "test: trigger EDPA sync workflow" && git push
```

Pak otevři `https://github.com/<org>/<repo>/actions` a sleduj:

| Workflow | Očekávaný stav |
|---|---|
| `Sync Git -> GitHub Projects` | ✓ Success (běží na push event) |
| `Sync GitHub Projects -> Git` | nemusí běžet (čeká na další `*/30` cron tick v business hours Po-Pá 8-18, nebo manual dispatch) |

Pro otestování druhého směru otevři `Actions → Sync GitHub Projects -> Git → Run workflow`
a sleduj, že po cca 20-40 s vznikne commit s tvojí změnou v `.edpa/backlog/<type>/<id>.yaml`.
Alternativně posuň issue card na Project boardu a počkej na další business-hours cron tick
(max 30 min latence v pracovní době; mimo ni se sync pozastaví).

### Co když to nefunguje

| Symptom | Příčina | Fix |
|---|---|---|
| `::warning::EDPA_TOKEN secret not configured` v logu | Secret se jmenuje špatně | Přejmenuj na přesně `EDPA_TOKEN` |
| `HTTP 403` na GraphQL mutaci | PAT nemá `project: read+write` | Edit token → přidej Projects org permission |
| `HTTP 404` na GH Project | PAT nemá repo permission na ten konkrétní repo | Edit token → Repository access → zahrň repo |
| `Please tell me who you are` při git commit | Workflow nemá git config step (legacy verze) | Updatuj `edpa-sync-projects-to-git.yml` na ≥ v1.17.1 |
| Workflow naskočí, ale 0 změn pulluje | PAT je z personal accountu, ne z org member | Vytvoř nový s Resource owner = org |

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

## 7. Pokud token nemůžeš nastavit (manuální fallback)

V první iteraci pilotu (a nebo když ti vyprší PAT mezi rotacemi),
sync můžeš dělat ručně:

```bash
# Před každým týdenním close:
python3 .edpa/engine/scripts/sync.py pull --commit

# Po každé úpravě .edpa/backlog/*.yaml:
python3 .edpa/engine/scripts/sync.py push
```

Tahle cesta nevyžaduje secret — používá tvůj lokální `gh auth login`
token. Funguje, ale:
- Žádný near-realtime sync z Projectu zpět do gitu (manuální `pull`)
- Riziko zapomenutí mezi PI close a další iterací
- Neškáluje na 4+ -člennou pilot tým, protože každý člen by musel
  spustit `pull` před svojí prací

**Doporučení:** manuální fallback je OK pro první 1-2 iterace pilotu,
než si nastavíš PAT. Pak přejdi na automated.

## 8. Classic PAT (legacy varianta)

Pokud z nějakého důvodu fine-grained nemůžeš použít (např. org policy
restrikce, fine-grained nevyřízené org approval requests), klasický PAT
funguje taky:

1. *Settings → Developer settings → Personal access tokens → Tokens
   (classic) → Generate new token (classic)*
2. **Scopes:** zaškrtni:
   - `repo` (full control of private repositories)
   - `project` (read+write GitHub Projects)
   - `read:org` (read org membership)
   - `workflow` (update workflow files)
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
A: Workflow začne fail-ovat. PI close manuálně přes `sync.py pull`
+ `/edpa:close-iteration` (skill běží lokálně, nepotřebuje secret).
Pak rotace tokenu a re-push.

---

**Související dokumenty:**
- [Pilot runbook](https://github.com/technomaton/edpa/blob/main/docs/kashealth-pilot/KASHEALTH-PILOT.md)
- [`edpa-sync-projects-to-git.yml`](https://github.com/technomaton/edpa/blob/main/.github/workflows/edpa-sync-projects-to-git.yml) — event-driven sync (Project → Git)
- [`edpa-sync-git-to-projects.yml`](https://github.com/technomaton/edpa/blob/main/.github/workflows/edpa-sync-git-to-projects.yml) — push-triggered sync (Git → Project)
- [Step-by-step průvodce v kontextu plné instalace](/guide) — krok 5 z 11
