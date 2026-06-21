# D-29 — plan oprava: gate na `commit_author` mimo okno itemu

> **Pracovni plan, nic neimplementovano.** Pristupem je **axiom-preserving gate**,
> ne date-windowing router. Tento dokument **nahrazuje** velkou cast
> `docs/v2/d29-cesta2-impact.md` (viz sekce "Co padá ze starého reportu").
> Vsechna tvrzeni o kodu jsou overena proti zdroji (path:line).

## Model a axiom

EDPA stoji na neporusitelnem axiomu rozsahu:

- **Story se vejde do JEDNE iterace. Feature se vejde do JEDNOHO PI.** Tecka.
- Clenstvi itemu v iteraci je dane stitkem `iteration:`, ne datem jednotliveho
  signalu. Tuto pravdu kodifikuje `transitions.item_in_iteration`
  (`transitions.py:142-166`): Story/Defect/Task exact match, Feature PI-prefix,
  Epic/Initiative cross-PI vzdy `True`.

Z toho plyne **no-spillover** politika (viz pametova poznamka
*"Item types: delivery-tracked vs not"* a *"D-28 cross-iteration yaml_edit guard"*):

- Kredit je **omezeny oknem te iterace, ktere item patri**. Prace, jejiz `at:`
  lezi **mimo** toto okno (typicky po konci iterace), se loguje **jen pro audit
  s vahou 0** — nikdy se nepreklapi do jine iterace, nikdy se neprepoctava.
- `at:` se pouziva jako **GATE** (uvnitr vlastniho okna itemu → vaha zustava;
  mimo → vaha 0), **NE jako router**.
- **Dusledek:** uzavrene iterace zustavaji **nemenne** — zadny recompute, zadna
  migrace snapshotu, zadne deleni itemu pres iterace. Kdyz prace realne pretece,
  procesni odpoved je **rozdelit ji na novou Story/Feature v dalsi iteraci**
  (+ pripadne rucni/retroaktivni zalogovani), ne chytra atribuce.

Tento model autor (jurby) zvolil misto drive navrzene "Cesty 2" (date-windowing),
kterou **odmitl**.

---

## Zmenšený rozsah D-29

D-29 je cross-iteration leak signalu `commit_author`: commit udelany behem iterace
N, ktery sahne na backlog item patrici jine iteraci M, kredituje autorovi plnou
vahu (~2.78) na M, protoze kreditni cesta je date-blind.

**Kde leak vznika:**

- `local_evidence.build_signals` (`local_evidence.py:243-302`) emituje za KAZDY
  dotceny item `commit_author` s `weight = weights.get("commit_author", 2.78)` a
  `at = iso` (author date commitu), bez ohledu na to, ke ktere iteraci item patri.
- Itemy se odvozuji z `detect_items` (`local_evidence.py:206-222`) — z ID v
  subjectu/body i ze **zmenenych cest** `.edpa/backlog/{type}/X-N.md`. Bulk-edit
  ciziho (treba uzavreneho) storyho tedy strhne `commit_author` i na nej.
- Engine kredit cte **date-blind**: `load_backlog_items` (`engine.py:482-547`)
  cte `contributors[].cw` verbatim; `cw` spocital `aggregate_signals`
  (`detect_contributors.py:493-553`) jako soucet **vsech** vah `commit_author` v
  `evidence[]`, a item je nabucketovan do iterace pouze pres stitkovy
  `item_in_iteration`. Engine `commit_author` **nikdy nedate-windowuje** — i
  synteticka story-activity polozka cte `contributors[]` verbatim
  (`engine.py:793-796`).

**Asymetrie, kterou D-29 uzavira:** engine UZ date-windowuje `state_transition`
(`engine.py:689`) a `yaml_edit` (`engine.py:724`) pres `_in_window`
(`engine.py:640-653`), ale `commit_author` ne. D-28 zavedl write-side
zero-weight guard pro `yaml_edit` (`_neutralize_foreign_yaml_edit`,
`local_evidence.py:437-473`), ale `commit_author` z nej vedome vynechal
(komentar `local_evidence.py:455-457` + `:466-472`: guard filtruje
`s.get("type") == "yaml_edit"` na radku 468).

**Co je oprava (presne):** rozsirit zero-weight guard tak, aby `commit_author`
signal na itemu M byl **neutralizovan** (vaha 0 + tag `out_of_iteration`,
jen audit), kdyz `at:` commitu lezi **mimo vlastni okno itemu M**. Zadna zmena
enginu (viz nize).

---

## Přesné pravidlo + reconciliation s D-28

### Trace soucasneho D-28 guardu (cim presne zeruje)

`_neutralize_foreign_yaml_edit(item, sigs, item_path, target_iteration)`
(`local_evidence.py:437-473`) zeruje signal tehdy, kdyz:

1. `target_iteration` je pravdive (`:458-459`), A
2. `item.iteration` neni prazdne (`:460-462`), A
3. `item_in_iteration(item_type, item_iter, target_iteration)` je **False**
   (`:465-466`) — tj. item PROKAZATELNE patri jine iteraci nez `target_iteration`.

`target_iteration` je u obou volajicich **iterace COMMITU**, ne itemu:

- `cmd_materialize` (`local_evidence.py:511`): `target = iteration_id`
  (materializovana iterace = okno, ktere se prave scanuje).
- post-commit hook (`local_evidence.py:662-683`): `target = commit_iter`,
  rozliseny pres `find_iteration_for_timestamp(edpa_root, author_date)`
  (`transitions.py:169-188`).

### Je rozsireni guardu ekvivalentni "gate dle vlastniho okna itemu"?

**Ano, prakticky ekvivalentni — bez vyjimky pro aktivni iterace.** Pri **bezmezernem
kalendari** (viz invariant v rozhodnuti #2) je gate predikat **presne "vlastni okno
itemu"**; jediny zbytkovy `None` je na **kraji cele timeline projektu** (commit pred
prvni iteraci nebo po posledni), kde se signal nechava v plne vaze jako dokumentovany
shovivavy fallback. Trace na konkretu (presne situace z D-28 testu, jen sledujeme
`commit_author` misto `yaml_edit`):

> Iterace: `PI-2026-1.1` = 1.–30. 4. (uzavrena), `PI-2026-3.1` = 15.–30. 6.
> `S-1.iteration = PI-2026-1.1`, `S-2.iteration = PI-2026-3.1`.
> Cervnovy commit (author date 18. 6., spada do okna 3.1) bulk-edituje OBA storye.
> `find_iteration_for_timestamp(18.6.)` → `commit_iter = PI-2026-3.1`.
>
> - **S-1** (patri 1.1): `item_in_iteration("Story", "PI-2026-1.1", "PI-2026-3.1")`
>   → `False` → `commit_author` na S-1 se **vynuluje** + `out_of_iteration`.
>   To je presne spravne: 18. 6. je MIMO okno S-1 (1.1 skoncila 30. 4.).
> - **S-2** (patri 3.1): `item_in_iteration("Story", "PI-2026-3.1", "PI-2026-3.1")`
>   → `True` → plna vaha. 18. 6. je UVNITR okna S-2. Spravne.

Proc to funguje jako "gate dle okna itemu": pro Story/Defect/Task plati
`item_in_iteration == True` **prave tehdy**, kdyz `item.iteration == commit_iter`.
A `commit_iter` je iterace, do jejihoz **okna** spada `at:` commitu. Takze:

```
item_in_iteration(item) == True
  ⇔ item.iteration == commit_iter
  ⇔ at: commitu spada do okna iterace, ktere item patri
  ⇔ at: je UVNITR vlastniho okna itemu        (pro exact-match typy)
```

Tedy "neguj kdyz `item_in_iteration == False`" = "neguj kdyz `at:` je mimo vlastni
okno itemu". **Cilem proto NENI psat novy predikat nad okny itemu — staci sundat
`yaml_edit`-only filtr** a nechat zaroven bezet stavajici `find_iteration_for_timestamp`
gate. Pro Feature funguje analogicky pres PI-prefix (commit kdekoli v PI ⇒ `True`).

### Doporuceny predikat

Misto tvrdeho odstraneni `yaml_edit` filtru doporucuji **generalizovat guard na
jakykoli VAZENY signal** (viz nize "Generalizace") s jednou vyjimkou typu, ktere
maji byt date-immune. Konkretni predikat uvnitr smycky (`local_evidence.py:467-472`):

```
GATED_TYPES = {"yaml_edit", "commit_author", "manual:commit_message",
               "agent_contribution"}
for s in sigs:
    if s.get("type") in GATED_TYPES and s.get("weight"):
        s.setdefault("raw_weight", s["weight"])  # zachovej puvodni vahu pro audit
        s["weight"] = 0
        s.setdefault("tags", []).append("out_of_iteration")  # dedup jako dnes
```

`raw_weight` se nese **vzdy** (nejen pri vynulovani): `build_signals` ho nastavuje
= puvodni vaha na `commit_author` i ostatnich GATED_TYPES, takze uvnitr okna plati
`weight == raw_weight`. Pri vynulovani guard nastavi `weight = 0`, ale `raw_weight`
= puvodni vaha **zustava** — presne jak uz dnes nese `raw_weight` `yaml_edit`
(materializace: `local_evidence.py:427` cte `s.get("raw_weight")`; guard
`:467-472` zeruje jen `weight`).

Predpoklady (`target_iteration` pravdive, `item.iteration` neprazdne,
`item_in_iteration == False`) zustavaji beze zmeny pred smyckou — funkce uz je
takto strukturovana. Funkci je vhodne prejmenovat na
`_neutralize_foreign_signals` (zachovat alias / docstring kvuli D-28 historii).

### Generalizace na vsechny vazene signaly

Vyctove vazene signaly nesouci `at:` (vsechny z `build_signals`,
`local_evidence.py:261-301`):

| typ signalu | `at:` zdroj | gate? | proc |
|---|---|:---:|---|
| `commit_author` | author date commitu (`%aI`) | **ANO** | jadro D-29 |
| `manual:commit_message` (`/contribute`) | author date commitu | **ANO** | retroaktivni `/contribute` v cizi iteraci by jinak kreditoval naslepo; `at:` = datum commitu, ne prace |
| `agent_contribution` | author date commitu | **ANO** | AI prace je take delivery; stejny leak |
| `yaml_edit` | `detected_at` | ANO (uz dnes) | D-28 |
| `state_transition` | `changed_at` | n/a | vaha 0 vzdy, `aggregate_signals` ho preskoci |

**Doporuceni: generalizovat** — gate VSECHNY vazene signaly, ne jen `commit_author`.
Vyhody:
- Konzistence: jeden write-side guard pro celou kreditni vahu.
- **Rozpousti "Problem 2"** (date-blindness i UVNITR spravne iterace): kazda
  vaha mimo okno itemu se stane 0, takze nezustane zadna cesta, kterou by
  out-of-window prace prosakovala.
- `manual:commit_message` a `agent_contribution` jsou stejne nachylne jako
  `commit_author` (stejny `at:`, stejny `detect_items` puvod).

GH-side signaly (`pr_reviewer`, `issue_comment`, `manual:pr_comment`) tento hook
**neemituje** (`local_evidence.py:14-17`; tvori je volitelny CI workflow). Jejich
`at:` je dnes detection-time, ne datum review/merge — gate na ne by byl
nepresny a je **mimo rozsah D-29** (poznamka do "Otevrene otazky").

### Potvrzeni: zadna zmena enginu / aggregate_signals

Neni potreba. `aggregate_signals` (`detect_contributors.py:506-521`) ma na radcich
511-512 `if not sig.get("weight"): continue` — **nulova vaha se preskoci** uz dnes
(stejne jako `state_transition`). Vynulovany `commit_author` tedy:
- nevstoupi do `contribution_score` ani do `cw` (`:521`, `:543`),
- nezmeni `load_backlog_items` cteni `cw` (`engine.py:541-546`),
- zustane fyzicky v `evidence[]` s `raw_weight` = puvodni vaha pro audit (stejne
  jako `yaml_edit`; viz rozhodnuti nize o reverzibilite — `raw_weight` se nese vzdy).

Engine `_in_window` zustava jak je; nemusime pridavat windowing `commit_author` do
enginu, protoze guard ho vynuluje **pred** zapisem do `contributors[]`.

---

## Co padá ze starého reportu

`docs/v2/d29-cesta2-impact.md` byl napsan pro **odmitnuty routing model** (Cesta 2).
Pod gate modelem padaji tyto jeho zavery (oznacit je v tom dokumentu jako
**superseded-by `docs/v2/d29-plan.md`**):

- **Breaking changes #1, #2, #3, #4, #5, #7, #8, #9, #11, #12** (sekce "Breaking
  changes"): "vsechna cisla se zmeni", item ve vice reportech (split),
  item s nula signaly se vynecha, **prepocet uzavrenych iteraci**, neporovnatelne
  snapshoty, zmena `ai_delivery_ratio`, retroaktivni `/contribute` routing,
  throughput/SP rozpor, tz off-by-timezone, re-kalibrace vah. Gate model nic z
  toho nedela — uzavrene iterace zustanou nemenne, item se nesplituje, cisla se
  zmeni jen o leak, ktery NEMEL existovat.
- **Davky B7 a B8** (recompute/snapshot migrace, immutability lock, backfill
  verzovani, migracni flag): **DROPPED**. Nemennost je dana tim, ze nic
  neprepocitavame; zadny zamek netreba.
- **JS-split / renormalizace pres okna** (rozhodnuti #3, breaking #2): **DROPPED**.
  Item nikdy nepretece do dvou oken — axiom to zakazuje.
- **Routing aggregator change** (`aggregate_signals`/`load_backlog_items` na
  per-window): **DROPPED**. Zadna zmena enginu/agregatoru.
- **Vetsina z 11 semantickych rozhodnuti** (#1 keying reportu, #2 precompute vs
  live, #3 JS-split, #4 okenkovani kapacity, #5 prepocet uzavrenych, #10
  throughput dual-view, #11 verzovaci flag): **DROPPED nebo bezpredmetne**.
  Zustavaji relevantni jen ozveny #6 (gap/fallback) a #7/#8 (blank-iteration,
  cross-PI Epic), ktere resime nize jako "otevrena rozhodnuti".
- **Tabulka dotcenych oblasti** (reports-outputs, consistency-invariant,
  ai-attribution, flow-metrics, pi-board, autocalibration-corpus,
  methodology-docs sweep, mcp-tools, commands-skills): vetsinou **bezpredmetna** —
  gate nemeni zadne cislo krome odebrani leaku, takze tyto subsystemy nevyzaduji
  zasah. Jediny realny presah: D-28 guard a jeho testy (uz existuji).

**Co ze stareho reportu ZUSTAVA platne** (a je uz vyreseno mimo D-29):
- D-30 (tz-safe `parse_iteration_dates` / `find_iteration_for_timestamp`) — UZ
  SHIPPED. Stary report to mel jako "5 mechanickych chyb"; gate je na tom zavisly
  a ted jsou helpery spolehlive (`transitions.py:116-139`, `:169-188`).

---

## Otevřená rozhodnutí

### 1. Cap jen na KONCI iterace, nebo zerovat i prace PRED zacatkem?
Stavajici `item_in_iteration` je date-blind: u exact-match typu vraci `True` pro
celou iteraci itemu, takze guard pres `commit_iter` automaticky zeruje
**oboustranne** (commit pred i po okne itemu spada do jine iterace nebo do None).
- **Doporuceni: zerovat oboustranne (symetricky).** Prace zalogovana driv, nez
  Story do sve iterace vstoupila, je stejne "mimo okno" jako prace po konci.
  Symetrie je zadarmo dusledkem `item_in_iteration` + commit-iteration gate; nic
  navic kodit. (Pokud by autor chtel tolerovat early work, je to explicitni
  vyjimka — viz "Otevrene otazky".)

### 2. Mezi-iteracni / okrajove commity (`at:` v zadnem okne → `find_iteration_for_timestamp` vraci None) — **VYRESENO (invariant)**
**Toto neni politicke rozhodnuti, ale invariant kalendare.** Iterace jsou definovane
**OD-DO daty** (`start_date`/`end_date`), default 1 tyden po-ne, a jsou **souvisle**:
`end_date` iterace X = den pred `start_date` iterace X+1. Pri takovem **bezmezernem
kalendari neexistuje mezera mezi iteracemi** — `find_iteration_for_timestamp` vrati
`None` **vyhradne na kraji cele timeline projektu** (commit pred `start_date` prvni
iterace nebo po `end_date` posledni), nikdy mezi aktivnimi iteracemi. Mezi-iteracni
mezera (napr. iterace konci v patek, dalsi zacina v pondeli, So/Ne nepokryto) je
**chybna konfigurace kalendare**, ne normalni stav.

- **Dusledek:** za bezmezerneho kalendare je gate predikat **presne "vlastni okno
  itemu"**, bez prakticke vyjimky. Drivejsi vyhrada, ze guard "neni presne vlastni
  okno itemu pro gap commity", tim **odpada**.
- **Okrajovy `None` (kraj timeline):** ponechat soucasne chovani — `target_iteration
  is None` → guard no-opuje (`local_evidence.py:458-459`) → signal si nechava plnou
  vahu. `item_in_iteration(.., None)` vraci `True`, takze je to **dokumentovany
  shovivavy fallback** pro commit pred prvni / po posledni iteraci. **Nezavadet
  "nejblizsi predchozi okno" fallback** — to by byl router, ktery model zakazuje.
- (Okrajova poznamka) Zanedbatelny podsekundovy seam: konec okna je 23:59:59, dalsi
  zacina 00:00:00. Pripadne uzaviratelne pozdeji pres porovnani `< next_start`, mimo
  rozsah D-29.

### 3. Epic / Initiative cross-PI (`item_in_iteration` vraci vzdy `True`)
Strategicke itemy legitimne zabiraji cele PI a vic. Guard u nich nikdy nezeruje.
- **Doporuceni: VZDY nechat (negate).** Je to v souladu s axiomem — Epic/Initiative
  nejsou vazane na jednu iteraci, takze "mimo okno" pro ne nedava smysl. Ponechat
  `item_in_iteration` always-True vetev (`transitions.py:165-166`) jako gate-bypass.
  Pripadne PI-okno gating pro Epic je samostatne (vetsi) rozhodnuti mimo D-29.

### 4. Itemy s prazdnym `iteration:` (D-28 je nechava netknute)
- **Doporuceni: zachovat chovani D-28 — netknout** (`local_evidence.py:460-462`).
  ~Polovina realnych stories/defektu je bez `iteration:`; jejich in-window prace
  je legitimni a guard zeruje jen PROKAZATELNE cizi itemy. Tohle plati pro
  `commit_author` uplne stejne jako pro `yaml_edit` — zadna zmena.

---

## Testy

Zrcadlit existujici D-28 guard testy (`tests/test_local_evidence.py`) pro
`commit_author`. Nove testy:

1. `test_materialize_zero_weights_cross_iteration_commit_author` — zrcadlo
   `test_materialize_zero_weights_cross_iteration_yaml_edit`
   (`test_local_evidence.py:450`): cervnovy commit v okne 3.1 edituje S-1 (∈ 1.1)
   i S-2 (∈ 3.1); `commit_author` na S-1 ma `weight == 0` + `out_of_iteration`,
   na S-2 plnou vahu, nikdy netagovany. **Navic asserce, ze vynulovany
   `commit_author` na S-1 si drzi puvodni `raw_weight`** (= weights["commit_author"],
   ~2.78) pro audit — zrcadlo `raw_weight` asserce u `yaml_edit` (`:497`).
2. `test_post_commit_hook_zero_weights_cross_iteration_commit_author` — zrcadlo
   `test_post_commit_hook_zero_weights_cross_iteration_yaml_edit`
   (`test_local_evidence.py:533`): stejny scenar pres LIVE hook (`_run_emitter`).
3. `test_post_commit_hook_keeps_commit_author_on_unassigned_item` — zrcadlo
   `test_materialize_keeps_yaml_edit_on_unassigned_item`
   (`test_local_evidence.py:506`): item bez `iteration:`, in-window commit →
   `commit_author` si drzi plnou vahu, netagovany.
4. `test_gate_neutralizes_manual_and_agent_signals_cross_iteration` — pokud se
   prijme generalizace: `manual:commit_message` a `agent_contribution` na cizim
   itemu se take vynuluji + `out_of_iteration` (na vlastnim ne).
5. `test_aggregate_skips_zeroed_commit_author` (do
   `tests/test_detect_contributors.py`) — explicitni regrese: vynulovany
   `commit_author` nevstoupi do `cw`/`contribution_score` (potvrzeni invariantu
   `detect_contributors.py:511-512`).
6. (volitelne) `test_gap_commit_commit_author_keeps_full_weight` — commit s `at:`
   v mezere mezi sprinty (`find_iteration_for_timestamp` → None) si drzi plnou
   vahu (kotvi rozhodnuti #2).

Existujici D-28 testy (`:450`, `:506`, `:533`, `test_item_in_iteration_*` `:435`)
musi **dal prochazet** beze zmeny — generalizace nesmi rozbit `yaml_edit` vetev.

---

## Kroky implementace

Maly rozsah, jeden sdileny soubor — **bez paralelnich worktree** (vse v
`local_evidence.py` + testy; serializovane, ale trivialni).

1. V `_neutralize_foreign_yaml_edit` (`local_evidence.py:437-473`) nahradit filtr
   `s.get("type") == "yaml_edit"` (radek 468) za clenstvi v `GATED_TYPES`
   (`yaml_edit`, `commit_author`, `manual:commit_message`, `agent_contribution`).
   Prejmenovat na `_neutralize_foreign_signals` (alias kvuli D-28 docstringu),
   upravit docstring (`:455-457`) — uz neni "scoped to yaml_edit only".
2. (Audit reverzibilita — ROZHODNUTO: `raw_weight` se nese vzdy) V `build_signals`
   (`local_evidence.py:261-301`) nastavit `raw_weight` = puvodni vaha na
   `commit_author` (a ostatnich GATED_TYPES), aby uvnitr okna platilo
   `weight == raw_weight`. Guard pri vynulovani nastavi `weight = 0`, ale
   `raw_weight` = puvodni vaha **zachova** + prida tag `out_of_iteration` — presne
   jako `yaml_edit` (`local_evidence.py:427`; test `:497` to overuje). Vynulovani
   je tim plne reverzibilni pro audit.
3. Napsat nove testy (sekce Testy) a overit, ze D-28 testy dal prochazeji.
4. `pytest tests/test_local_evidence.py tests/test_detect_contributors.py`.
5. Aktualizovat dokumentaci: kratky odstavec v `docs/methodology.md` (sekce D-28)
   a v `docs/audit-trail.md` o tom, ze gate nyni plati pro vsechny vazene
   delivery signaly. Oznacit `docs/v2/d29-cesta2-impact.md` jako superseded.

---

## Otevřené otázky na autora

1. **Generalizace ano/ne:** gate-ovat i `manual:commit_message` a
   `agent_contribution`, nebo striktne jen `commit_author` (uzsi D-29)?
   (Doporucuji generalizovat — rozpousti to Problem 2 a je to konzistentni.)
2. **Gap commits (rozhodnuti #2): ✅ VYRESENO — invariant bezmezerneho kalendare.**
   Iterace jsou souvisle OD-DO (`end_date` X = den pred `start_date` X+1), takze
   mezera mezi aktivnimi iteracemi neexistuje; `None` vznika jen na kraji timeline
   projektu, kde se nechava plna vaha (shovivavy fallback). Mezi-iteracni mezera je
   chybna konfigurace kalendare, ne normalni stav. Gate je tim presne "vlastni okno
   itemu", zadna prakticka vyjimka. Zadny "nejblizsi okno" router.
3. **Reverzibilita auditu: ✅ VYRESENO — `raw_weight` se nese vzdy.** `build_signals`
   nastavuje `raw_weight` = puvodni vaha na `commit_author` (a ostatnich GATED_TYPES),
   takze uvnitr okna `weight == raw_weight`; guard pri vynulovani nastavi `weight = 0`,
   ale `raw_weight` = puvodni vaha zachova + prida `out_of_iteration` — presne jako
   `yaml_edit` (`local_evidence.py:427`). Vynulovani je plne reverzibilni pro audit.
4. **Early work (rozhodnuti #1):** ma se prace zalogovana PRED zacatkem iterace
   itemu tolerovat (cap jen na konci), nebo zerovat symetricky? (Doporucuji
   symetricky — je to zadarmo z `item_in_iteration`.)
5. **GH-side signaly:** `pr_reviewer`/`issue_comment`/`manual:pr_comment` (CI
   workflow, ne tento hook) maji `at:` = detection-time. Mimo rozsah D-29, nebo
   zalozit navaznou polozku na spravny timestamp + gate i je?
6. **Backfill existujicich `commit_author` leaku:** historicke `evidence[]` se
   plnou vahou na cizich itemech zustanou (guard plati jen pro nove zapisy).
   Spustit `/edpa:materialize --all-iterations` k pregenerovani — ale to
   neprepise jiz zapsane `commit_author` (dedup dle `ref`). Chce autor jednorazovy
   re-neutralize sweep nad existujicimi `evidence[]`, nebo necha historii byt?
