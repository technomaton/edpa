# Dopadova analyza: Cesta 2 — date-windowing atribuce kreditu

> **⚠️ SUPERSEDED (D-29).** Tento dokument analyzoval *routing* model (Cesta 2),
> ktery autor ODMITL ve prospech axiom-preserving **gate** modelu — viz
> `docs/v2/d29-plan.md`. Zavery o "breaking changes", recompute uzavrenych
> iteraci, migraci snapshotu, JS-split a vetsine z 11 rozhodnuti odsud **uz
> neplati**. Ponechano jako zaznam analyzy, ktera k tomu rozhodnuti vedla.

> **Read-only analyza, nic neimplementovano.** Slouceni nalezu z 18 oblasti.
> Cesta 2 = o iteraci kazdeho kreditu rozhoduje `at:` timestamp jednotliveho
> evidence zaznamu, ne stitek `iteration:` itemu.

## Shrnuti rozsahu

Cesta 2 je **dokonceni uz castecne nasazeneho vzoru, ne greenfield refaktor**. Engine dnes uz date-windowuje `state_transition` a `yaml_edit` signaly pres `_in_window()` (`engine.py:665-727`), ale **Done-credit a commit_author cesta** cte `contributors[].cw` verbatim podle stitku `iteration:` itemu (`item_in_iteration` v `load_backlog_items`). Vznika tak skryta nekonzistence: gate+yaml_edit kredit se ridi datem signalu, commit_author a Done kredit stitkem itemu.

Cesta 2 sjednocuje obe vety. Zasah je **breaking** a saha napric celym stackem — od jadra agregace (`detect_contributors.aggregate_signals`, `engine.load_backlog_items` + `run_edpa`) pres reporty, payroll, snapshoty, ai_attribution, flow-metriky az po kalibracni korpus. Navic **pet mechanickych chyb zije uz dnes** (tz-clobber, vikendove mezery, naive datetime, `at:`-None fallback) a Cesta 2 je povysi z debug-vystupu na chyby vyplatniho reportu.

**Pred psanim kodu je nutnych 12 semantickych rozhodnuti autora** — bez nich nelze napsat ani test, ani implementaci.

---

## Dotcene oblasti

| Oblast | Dopad | Breaking | Effort | Risk |
|---|---|:---:|:---:|:---:|
| **engine-core** (aggregate_signals + load_backlog_items/run_edpa) | Jadro zmeny. `aggregate_signals` (`detect_contributors.py:493-553`) secita cele `evidence[]` slepe k `at:`; `load_backlog_items` (`engine.py:411-590`) bucket-uje dle stitku. Obe na per-signal `at:`-filtr. `cw` prestava byt globalni per-item a stava se per-item-per-window. | ano | L | high |
| **windowing-already-shipped-asymmetry** | Engine uz windowuje yaml_edit+state_transition (`engine.py:689,724`), Done/commit_author ne. C2 = sjednoceni. `_passthrough_contributors` + `load_story_activity_events` ctou contributors[] verbatim — stejna vada. | ano | L | high |
| **iteration-windows** (transitions.py) | `find_iteration_for_timestamp` (`:159-172`) dela linearni disk-scan per-signal bez cache. Chybi `load_all_iteration_windows` index. tz-handling nekonzistentni s `_in_window`. | ne | M | med |
| **window-boundary-precision-tz-and-gaps** | Pet chyb zive dnes: tz-clobber (`.replace` vs `.astimezone`), vikendove mezery (commit → `None` → tise zmizi), naive datetime v `annotate_with_iterations` (TypeError Py3.11+), `.replace` v `--since`. | ano | M | high |
| **evidence-d28** (emit + guards) | `_neutralize_foreign_yaml_edit` (D-28 guard) se stava nadbytecnym. D-29 leak se resi prirozene pres `at:`-okno — ale jen pro nove zaznamy; historicke bez `at:` zustanou. | ano | M | med |
| **reports-outputs** | Vsechna cisla videt uzivatelum se zmeni (derived_hours, team_total, timesheety, PI summary, payroll CSV, Excel). Jeden item se rozdeli do vice reportu. Plus bug `pi_close` cte `allocations[]` misto `people[]`. | ano | L | high |
| **consistency-invariant** | Aritmetika invariantu nepadne (ratio-normalizace), ale semantika jina. Rozhodnuti: kapacita pevna nebo pro-rate? | ano | L | high |
| **edge-semantics** (7 pripadu) | Blank-iteration, cross-PI Epic/Initiative, commity mimo okna, prepocet uzavrenych iteraci (porusi nemennnost `capacity_override.py:294`), split pres okna, legacy bez `at:`, flow_metrics stitek. | ano | L | high |
| **backfill-migration** | Kazdy item s historii produkuje jine contributors[] po re-runu. Uzavrene iterace se tise precisli. Nutny `--all-iterations` backfill, verzovani, zmrazeni snapshotu. | ano | L | high |
| **test-suite** | Padaji: oba D-28 testy, `test_report_equals_materialized_snapshot`, `test_aggregate_basic_three_persons` (placeholder `'detected_at':'t'`), refresh testy. ~15+ novych testu. | ano | L | high |
| **methodology-docs** | methodology, RUNBOOK, quick-start, playbook, KASHEALTH, evidence-detection, engine SKILL — vsechny popisuji 'report = itemy se stitkem' na desitkach mist. | ano | M | med |
| **mcp-tools** | Tenke obaly. Prime zasahy: `edpa_backlog` iteration filtr, `edpa_materialize` scope popis, ai_attribution delegace. Testy na stitkovy filtr se rozbiji. | ano | M | med |
| **commands-skills** | engine/reports SKILL, materialize/close-iteration/reconcile commands popisuji 'Done in iteration' stitkovy model. Stage 2b vola `detect_contributors --all-items` bez okna. | ano | M | high |
| **ai-attribution-duplicate-label-scoper** | `ai_attribution.py:60-99` ma vlastni kopii stitkoveho scoperu (ne `item_in_iteration`). Pod C2 `ai_delivery_ratio` prirazuje AI praci jinak nez engine prirazuje hodiny — dve cisla se rozejdou. | ano | M | med |
| **manual-contribute-and-agent-at-routing** | Retroaktivni `/contribute` v commitu I.2 opravujici praci z I.1 → kredit do I.2 (NESPRAVNE). `agent_contribution at:`=commit date, ne datum prace AI (lisi se pri amend/rebase). | ano | M | high |
| **flow-metrics-throughput-double-impl** | Tri stitkove implementace 'co patri do iterace' (flow_metrics, _sp_rollup, velocity/pi_metrics). Pod C2 trvaly rozpor 'kolik polozek vs kolik hodin'. | ano | L | high |
| **pi-board** | Board zobrazuje per-item cw, filtruje dle stitku — neprimy dopad. Pri per-iteration contributors nutny schema bump + rebuild. Jinak bez zmeny. | ne | S | low |
| **autocalibration-corpus-no-windowing** | `calibrate_signals.py` ladi `DEFAULT_WEIGHTS` na korpusu BEZ oken. Pod C2 engine vidi jen castecny rez — vahy jsou systemicky zkreslena reference (MAD 0.0869 neplatí). | ano | L | high |

---

## Breaking changes (konkretne)

1. **Vsechna cisla se zmeni** — derived_hours/osoba, team_total/iterace, timesheety, payroll CSV, Excel. Re-run na existujici data da jine vysledky.
2. **Jeden item ve vice reportech** (split). Item Done v PI-2026-1.1 s commity v PI-2026-1.0 presune Done-credit zpet do 1.0; item se stitkem 1.1 editovany v 1.2 kredituje v 1.2.
3. **Item Done s NULA signaly v okne se vynecha** z reportu (dnes zahrnut pres stitek-match).
4. **Uzavrene iterace prestanou byt nemennne** — re-run s nove pridanymi `at:` zaznamy tise precisli schvaleny report. `capacity_override.py:294` guard NESTACI.
5. **Existujici snapshoty neporovnatelne** — `payload_signature` vzdy jina; snapshot nenese semantickou verzi.
6. **D-28 guard nadbytecny** (`_neutralize_foreign_yaml_edit` + `out_of_iteration` tag + `weight=0`). Oba D-28 testy padaji.
7. **`ai_delivery_ratio` se zmeni** — AI prace dle `at:` okna `agent_contribution`, ne dle stitku.
8. **Retroaktivni `/contribute`** kredituje okno commitu s direktivou, ne okno puvodni prace.
9. **throughput count + SP-velocity zustanou stitkove**, derived_hours prejde na okna — report I.1 muze rikat 'throughput=5, velocity=40SP' ale hodiny pokryvaji jen cast polozek.
10. **Vikendove commity** padaji do `None` a pod C2 tise vypadnou z vyplatniho reportu.
11. **tz off-by-timezone** — commit +02:00 po 22:00 LOCAL v posledni den iterace = dalsi den UTC → vypadne nebo spadne do spatne iterace.
12. **`DEFAULT_WEIGHTS` zkalibrovany na per-item korpus** — pod C2 windowed MAD vyrazne vyssi; stare `calibration_corrections` inkompatibilni.
13. **Zmena signatury `cmd_all_items`** (povinny `iteration_id`) rozbije close-iteration Stage 2b + vsechny `test_refresh_all_contributors.py`.

---

## Semanticka rozhodnuti (musi udelat autor EDPA)

### 1. Klicovani reportu: cisty date-window nebo hybrid?
- **Moznosti:** (A) Cisty window — `load_backlog_items` prestane filtrovat stitkem. (B) Hybrid — `item_in_iteration` zustane jako Done-filtr (SAFe hierarchie), prida se druhy pruchod co orízne `signals[]` dle `at:`.
- **Doporuceni: (B) Hybrid.** Zachovat `item_in_iteration` jako Done-membership (jinak Story s pozdnim commitem skoci do drivejsi iterace, a Epic/Initiative cross-PI logika se ztratí), ale `cw` prepocitat z windowed subsetu. Epic/Initiative ale potrebuje explicitni `find_iteration_for_evidence_record`.

### 2. Kde sedi window-filtr: precompute nebo live?
- **Moznosti:** (A) Precompute v detect_contributors → novy orchestracni krok. (B) Engine filtruje live z `contributors[].signals[]` → rozbiji 'engine je pure reader'.
- **Doporuceni: (B) Live.** `contributors[].cw` se stava funkci(okno), pocita se v engine pres `_in_window`, **neprepisuje se zpet do souboru**. `detect_contributors` zustava cistym write-side nastrojem. Zadna duplikace stavu, zadne stale precompute. `aggregate_signals` si pak ani nemusi brat window parametr.

### 3. Deleni JobSize pres dve okna
- **Moznosti:** (A) Proporcionalni split dle vahy/poctu signalu. (B) Cele js v obou + varovani. (C) Cele js jen do iterace s vetsinou.
- **Doporuceni: (A) Proporcionalni split** dle podilu `contribution_score` v okne. Jen tak zustane `Sigma DerivedHours[P,*] == Capacity[P,I]` platny. (B) porusuje invariant, (C) tise zahazuje praci. **Nejvetsi matematicke rozhodnuti.**

### 4. Okenkovat i kapacitu?
- **Moznosti:** (A) Pevna kapacita. (B) Pro-rate dle vahy evidence v okne.
- **Doporuceni: (A) Pevna.** Jednodussi, invariant testy projdou formalne (nove fixture). Pro-rate (B) meni vzorec, invariant i ~12 testu a vyzaduje rozhodnuti o iteration-level override. Zvolit (A), pokud neni explicitni potreba pro-rate.

### 5. Prepocet uzavrenych iteraci
- **Moznosti:** (A) Nemennnost — snapshot se pri close zapecetí. (B) Vedomy re-run s `--force`.
- **Doporuceni: (A) Zapecetit.** Engine pri re-runu uzavrene iterace cte zapeceteny snapshot misto live prepoctu, nebo varuje pri divergenci. Pridat `evidence_routing` + schema verzi do snapshotu.

### 6. Fallback pro `at:` mimo vsechna okna (vikendy/mezery)
- **Moznosti:** (A) Zahodit. (B) Nejblizsi predchozi iterace. (C) Bucket 'unattributed'. (D) Rozsirit okna bez mezer.
- **Doporuceni: (D) kalendar bez mezer** (end na nedeli pred dalsim sprintem) NEBO (B). (D) eliminuje cely problem a nemeni semantiku. (A) tise zahazuje vyplatu — nepripustne. Nutny ADR.

### 7. Blank-iteration + cross-PI Epic/Initiative
- **Doporuceni:** Blank-item: (A) kreditovat dle `at:` automaticky (zlepseni). Epic/Initiative: zavest `find_iteration_for_evidence_record(signal, item_type)` — signaly s `at:` do sve iterace, mimo okna do nejblizsi iterace v ramci PI.

### 8. Backward-compat pro zaznamy bez `at:`
- **Doporuceni: (C) Migrace + (B) runtime fallback.** Spustit `--materialize --all-iterations` pred nasazenim. Pro zbytkove zaznamy bez `at:` pouzit `item.iteration:` stitek (ne 'kazde okno' — to zdvojuje kredit). Pure tolerantni fallback (`True`) je nebezpecny pro kalibraci.

### 9. Semantika `at:` pro manual/agent signaly
- **Doporuceni: (A) pridat `date:` parametr** do `/contribute` (`_CONTRIBUTE_RE`, `local_evidence.py:72-74`), validovat. Pro `agent_contribution` ponechat `%aI` s poznamkou. Bez (A) retroaktivni korekce kredituje spatnou iteraci — kolize s `docs/contribute-directive.md:107-113`.

### 10. throughput/SP-velocity vs derived_hours
- **Doporuceni: (B) Dual-view** s jasnou dokumentaci. SP-velocity je planovaci metrika, derived_hours atribuce usili — smichat by zvysilo zmatek. `_sp_rollup` je sdilen i enginem → zmena opatrne (novy fn, ne prepis).

### 11. Verzovani / migracni prepinac
- **Doporuceni: (B) Opt-in flag** `evidence_routing: date-window | iteration-label` v `edpa.yaml`. Umozni pilotu migrovat vedome. Flag se zapise i do snapshotu. **Pro existujici projekty default OFF**, aby se neretrahovaly schvalene vykazy.

---

## Dopad na testy

**Padaji bez zmeny:**
- `test_local_evidence.py:450` + `:533` — D-28 guard (`out_of_iteration` tag, `weight=0`); C2 nahrazuje `at:`-filtrem.
- `test_detect_contributors.py:163` `test_aggregate_basic_three_persons` (+ dalsi) — signaly maji placeholder `'detected_at':'t'` misto ISO.
- `test_evidence_single_source.py:79` `test_report_equals_materialized_snapshot` — invariant `file_cw==report_cw` neplatí pro windowed subset.
- `test_mcp_server.py:203/492` — assert na stitkovy filtr.
- `test_refresh_all_contributors.py` — pri zmene signatury `cmd_all_items`.

**Padaji pri pro-rate kapacite (pokud zvolena):** ~12 invariant testu — `test_invariants.py:16/62/76/136`, `test_capacity_overrides.py:108/124/182`, `test_gate_allocation.py:243`, `test_engine_properties.py:82/120/219/238`.

**Slaba mista (neodhali chybu):** `test_iteration_window_filter` (`test_gate_allocation.py:147`) pouziva naive ISO bez offsetu → tz-bug netestuje. `test_engine_properties.py` + `generate_demo_data` (`engine.py:968`) bez `at:` → windowing nepokryje.

**Nove testy:** `test_aggregate_signals_window_filters_by_at`, `test_item_split_across_two_iterations` (split + JS-split + renorm), `test_zero_evidence_in_window_gives_zero_derived`, `test_gate_event_window_by_changed_at`, `test_parse_iteration_dates_tz_aware`, `test_in_window_offset_boundary`, `test_find_iteration_for_timestamp_gap`, `test_annotate_with_iterations_offset`, `test_ai_attribution_evidence_window_scoping`, `test_flow_metrics_window_vs_label`, `test_calibrate_windowed_mad_differs_from_per_item`, `test_closed_iteration_immutable_under_date_windowing`, `test_at_missing_fallback`, `test_contribute_directive_at_routing`.

---

## Dokumenty k prepsani

**Core:** `docs/methodology.md` (§5.3, §5.4, §5.5, §6.2, D-28 sekce), `docs/v2/concept.md`, **`docs/v2/decisions.md` (NOVY ADR)**, `docs/RUNBOOK.md`, `docs/quick-start.md`, `docs/playbook.md`, `docs/evidence-detection.md`, `docs/audit-trail.md`, `docs/contribute-directive.md`, `docs/mcp.md`, `CHANGELOG.md`.

**Pilot + proposals + E2E:** `docs/kashealth-pilot/KASHEALTH-PILOT.md`, `docs/proposals/v1.17-yaml-edit-calibration-corpus.md`, `docs/E2E-TEST-PLAN.md`, `docs/E2E-SKILLS-TEST-PLAN.md`.

**Plugin:** `plugin/skills/engine/SKILL.md`, `plugin/skills/reports/SKILL.md`, `plugin/skills/autocalib/SKILL.md`, `plugin/commands/{materialize,close-iteration,reconcile}.md`, `plugin/edpa/templates/cw_heuristics.yaml.tmpl`, `plugin/README.md`.

---

## Davkovy implementacni plan

> `worktree_isolatable=false` = sdileny soubor (`engine.py` / `detect_contributors.py` / `local_evidence.py`) → serializace, nelze paralelne.

| ID | Davka | Depends | Paralelne? | Effort |
|---|---|---|:---:|:---:|
| **B0** | Semanticka rozhodnuti + ADR (autor, pred kodem) | — | ano | M |
| **B1** | iteration-windows helpery + tz/gap/naive fixy (`transitions.py`) | B0 | ano | M |
| **B2** | **Engine-core**: windowed cw v `load_backlog_items` + `run_edpa` + story_activity + passthrough | B0, B1 | **ne** | L |
| **B3** | Evidence-emit + D-28/D-29 cleanup (`local_evidence.py`) | B0, B2 | **ne** | M |
| **B4** | `ai_attribution.py` — sjednotit scoper + window filtr | B0, B2 | ano | M |
| **B5** | flow-metrics + SP-velocity dual-view (`mcp` + `_sp_rollup` + `velocity` + `pi_metrics`) | B0, B1 | ano | L |
| **B6** | manual/agent `at:` routing — `date:` parametr + docs limitace | B0, B3 | **ne** | M |
| **B7** | Reports/outputs + payroll + explain + snapshots + `pi_close` bug-fix | B2 | **ne** | L |
| **B8** | Backfill + verzovani + zamek uzavrenych iteraci + migracni flag | B2, B3, B7 | **ne** | L |
| **B9** | Autokalibrace windowed corpus (`calibrate_signals.py`) | B0, B2 | ano | L |
| **B10** | MCP tools popisy + `edpa_backlog`/`materialize` scope | B2, B4 | ano | M |
| **B11** | Commands + skills prepis (workflow popisy) | B2, B3, B7 | ano | M |
| **B12** | Methodology + pilot docs sweep | B2, B7, B8 | ano | M |
| **B13** | PI-board (jen pokud per-iteration contributors) | B0, B7 | ano | S |

**Kriticka cesta (serializovana, sdilene soubory):** `B0 → B1 → B2 → B3 → B7 → B8`. Tyto davky sahaji na `engine.py` / `detect_contributors.py` / `local_evidence.py` a nelze je delat paralelne.

**Paralelizovatelne (vlastni worktree):** `B1`, `B4`, `B5`, `B9`, `B10`, `B11`, `B12`, `B13` — po splneni svych `depends_on`. Doporuceny postup: nejdriv B0 (rozhodnuti) → B1+B2 sekvencne na jadru, pak rozjet B4/B5/B9 paralelne (kazda jiny soubor) a docs davky (B11/B12) na konci.

---

## Otevrene otazky na autora

1. **Varianta B (live filtr):** souhlasi autor, ze `contributors[].cw` v souboru zustane 'celoitemovy souhrn' a engine ho ignoruje ve prospech live windowed vypoctu?
2. **JS-split pri 3+ oknech:** linearni split podle `score` je deterministicky, ale je spravny i pro Epic s mnoha malymi signaly napric celym PI?
3. **Nemennnost vs opozdeny hook:** snapshot zapeceteny pri close → commit pushnu den po close → kredit propadne. Prijatelne, nebo grace-period?
4. **Vikendove mezery (varianta D):** rozsirit okna bez mezer vyzaduje zmenu existujicich `*.yaml` end_date. Migracni skript, nebo na uzivateli pri create-pi?
5. **DST + Python verze:** DST prechod (CEST→CET) in-scope nebo known limitation? `fromisoformat` na date-only stringu se chova jinak Py3.7-3.10 vs 3.11+ — overit min. verzi v CI.
6. **GH-sourced signaly:** `pr_reviewer`/`issue_comment` maji `at:`=`utc_now_iso()` (detection time), ne datum review/merge. Hledat lepsi timestamp?
7. **Re-kalibrace:** akceptovatelne nasadit C2 se starymi per-item vahami a re-kalibrovat pozdeji, nebo windowed kalibrace soucasti stejneho release?
8. **KASHEALTH pilot:** po re-runu se uzavrene PI-2026-1.* zmeni — zadouci oprava (D-29 leak) nebo nezadouci retrakce? Pokud retrakce vadi → flag default OFF.
9. **`cmd_all_items`:** prejmenovat na `cmd_per_iteration` (povinny `iteration_id`), nebo deprecated? Ovlivnuje kolik testu se prepisuje + zda Stage 2b dostane window parametr.

---

**Celkovy risk: high. Celkovy effort: XL.**