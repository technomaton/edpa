# GOVERNANCE ŘEŠENÍ

## PRO PROJEKT Medical Platform a Datový e-shop

CZ.01.01.01/01/24_062/0007440 · OP TAK

**EDPA — Evidence-Driven Proportional Allocation**

*Capacity derivation from delivery evidence*

SAFe 6 Governance · WSJF · Epic Hypothesis · Kill Criteria · Predictability

7 GitHub Actions · Governance Labels · AI Snapshot Layer

Tooling: Microsoft 365 Teams + GitHub (bez Jira, bez Confluence)

Identita: kashealth.cz · Hybridní model (5 členských + guest)

**ČVUT FBMI + Medicalc software s.r.o.**

Verze 3.0 (merged) | Březen 2026

Zpracoval: Jaroslav Urbánek, Lead Architect / Vedoucí VaV

Určeno pro: Vedení projektu, ČVUT FBMI, IT ČVUT, Medicalc

---

## 1. Shrnutí a doporučení

> *Tento dokument definuje kompletní governance řešení pro projekt Medical Platform a Datový e-shop: tooling stack (M365 Teams + GitHub), identitu (kashealth.cz), metodiku vykazování (EDPA), SAFe 6 governance framework a implementační plán. Celkové náklady: ~1 520 Kč/měsíc za základní stack + volitelně AI API.*

Projekt zahrnuje týmy z ČVUT FBMI a Medicalc software s.r.o. se zaměřením budoucího spin-offu. Model stojí na pěti principech:

- GitHub jako single source of truth pro delivery metadata (kód, issues, hierarchie, workflow)
- EDPA (Evidence-Driven Proportional Allocation) místo timesheetů — nikdo neloguje hodiny
- Nezávislý Job Size a WSJF na každé úrovni hierarchie (Initiative -> Epic -> Feature -> Story)
- SAFe 6 governance: Epic Hypothesis Statement, Lean Business Case, Kill Criteria, Predictability
- Oddělení delivery metadata, capacity registry a evidence vrstvy

| Metrika | Hodnota | Poznámka |
|---|---|---|
| **Měsíční náklady** | ~1 520 Kč (66 $) | 15 uživatelů, M365 + GitHub + doména |
| **Náklady za 9 měs.** | ~13 700 Kč (596 $) | Duben–prosinec 2026 |
| **M365 licence** | 5x @kashealth.cz | Koordinátoři + reserve |
| **GitHub Team** | 8 vývojářů | 4 $/user/měs. |
| **Čas nasazení** | 1–2 dny | Vč. integrací a EDPA setup |
| **Metodika vykazování** | EDPA 1.0.0-beta | Dual-view: per-person + per-item |
| **Governance framework** | SAFe 6 inspired | Epic Hypothesis, WSJF, Predictability |

---

## 2. Tooling stack

Projekt používá GitHub-only governance model bez Jiry a Confluence. GitHub Issues + Projects + sub-issues (GA April 2025, 8 úrovní hierarchie) nahrazuje kompletní SAFe-like řízení.

### 2.1 Přehled nástrojů a nákladů

| Nástroj | Plán | Uživatelé | Měsíčně | 9 měs. |
|---|---|---|---|---|
| **M365 Business Basic** | 6 $/uživatel | 5 (členové) | 30 $ | 270 $ |
| **GitHub Team** | 4 $/uživatel | 8 (vývojáři) | 32 $ | 288 $ |
| **Doména kashealth.cz** | WEDOS, 160 Kč/rok | — | ~0,7 $ | ~8 $ |
| **CELKEM** | | 15 lidí | ~63 $ | ~566 $ |
| **CELKEM v Kč** | (kurz 23 Kč/$) | | ~1 520 Kč | ~13 700 Kč |

### 2.2 Co nahrazuje co

| Tradiční nástroj | Nahrazeno |
|---|---|
| **Jira** | GitHub Issues + Projects + sub-issues + issue types |
| **Confluence** | GitHub Wiki + /docs/ v repo + GitHub Pages |
| **Tempo / Everhour** | EDPA — evidence-driven allocation (odvozené hodiny) |
| **Jira Roadmaps** | GitHub Projects Roadmap view |
| **Jira Automation** | GitHub Actions (7 workflowů) |
| **Spreadsheet výkazy** | Action -> MD + JSON -> Excel pipeline + BankID |
| **Power BI / Grafana** | AI Snapshot Layer — JSON -> AI -> Markdown reporty |

---

## 3. Identita a Microsoft Teams

### 3.1 Doména kashealth.cz

Projekt používá vlastní doménu kashealth.cz registrovanou u WEDOS. 5 licencovaných M365 účtů pro koordinátory, ostatní se připojují jako hosté ze svých domácích organizací.

> *Klíčové omezení: Hosté v Microsoft Teams nemohou plánovat schůzky. Toto je hardcoded omezení na úrovni Entra ID. Proto koordinátoři potřebují plné členské účty.*

### 3.2 Hybridní identity model

| Role | Účet | Typ | Licence | Plán? | Org |
|---|---|---|---|---|---|
| **Lead Architect** | urbanek@kashealth.cz | Plný člen | M365 Basic | Ano | ČVUT |
| **DevSecOps Eng.** | tuma@kashealth.cz | Plný člen | M365 Basic | Ano | ČVUT |
| **PM / Batek** | batek@kashealth.cz | Plný člen | M365 Basic | Ano | ČVUT |
| **PM Medicalc** | pm@kashealth.cz | Plný člen | M365 Basic | Ano | MC |
| **Reserve** | (5. licence) | Plný člen | M365 Basic | Ano | — |
| **Vývojáři ČVUT (2)** | @cvut.cz | Guest/Shared | Zdarma | Ne | ČVUT |
| **Vývojáři MC (4)** | @medicalc.cz | Guest | Zdarma | Ne | MC |
| **Výzkumníci ČVUT** | @cvut.cz | Guest | Zdarma | Ne | ČVUT |

### 3.3 Požadavky na IT ČVUT

- B2B Direct Connect: Cross-tenant access v Entra ID pro sdílené kanály (~15 minut konfigurace)
- Organization Relationship: Exchange Online PowerShell pro sdílení free/busy (~10 minut)

Obě konfigurace jsou bezpečné a neovlivňují stávající IT infrastrukturu. Fallback: standardní guest přístup bez spolupráce IT.

---

## 4. EDPA — Evidence-Driven Proportional Allocation

> *Čas se neměří, odvozuje se. Člověk deklaruje kapacitu na období. Systém identifikuje work items, na nichž se prokazatelně podílel. Kapacita se ex post rozpadá poměrově mezi relevantní items podle Job Size a míry contribution.*

### 4.1 Tři vrstvy modelu

| Vrstva | Účel | Kde žije |
|---|---|---|
| **Operational Metadata** | Živá delivery data | GitHub Issues + Projects |
| **Capacity Registry** | Kapacita lidí, role, FTE, availability | YAML / JSON config v repo |
| **Evidence & Reporting** | Frozen snapshoty, výkazy, podpisy | /snapshots, /reports, /signed |

### 4.2 Source of truth

GitHub JE source of truth pro: issue hierarchii, ownership, status práce, zařazení do Planning Intervalu a Iterace, Job Size, WSJF inputs, review a merge trail, delivery audit trail.

GitHub NENÍ source of truth pro: hodinovou kapacitu osoby, FTE evidenci, derived hours za uzavřené období, podpisové stavy. Tyto informace vznikají a žijí v evidence vrstvě.

### 4.3 Vstupy modelu

| Vstup | Zdroj | Příklad |
|---|---|---|
| **Capacity[P, I]** | Potvrzeno při Iteration Planning | 40h |
| **RelevantItems[P, I]** | Automaticky z GitHub evidence | 6 items přes 3 úrovně |
| **JobSize[item]** | Custom field na issue | Fibonacci 1–20 |
| **ContributionWeight[P, item]** | Z evidence / manuální override | 0.15–1.0 |
| **RelevanceSignal[P, item]** | Normalizováno z Evidence Score | 0.25–1.0 |

### 4.4 Evidence detection

| GitHub signál | Evidence body | Typický CW | Poznámka |
|---|---|---|---|
| **Assignee na issue** | +4 | 1.0 | Owner |
| **/contribute příkaz** | +3 | 0.6 | Explicitní |
| **PR author referencující item** | +2 | 0.6 | Key contributor |
| **Commit s S-XXX / F-XXX / E-XXX** | +1 | 0.25 | Contributor |
| **PR reviewer** | +1 | 0.25 | Reviewer |
| **Issue / PR comment** | +0.5 | 0.15 | Consulted |

- Threshold relevance: Evidence Score >= 1.0
- Heuristika CW: nejsilnější signál určuje výchozí CW
- Manuální override: `/contribute @osoba weight:0.6`
- Commit count se nepřevádí na čas, jen pomáhá potvrdit relevanci

### 4.5 Výpočet — dvě varianty

> *Provozní (Simple):* `Score = JobSize × ContributionWeight`
>
> *Auditní (Full):* `Score = JobSize × ContributionWeight × RelevanceSignal`
>
> `DerivedHours[P, item] = (Score[P, item] / ΣScores[P, I]) × Capacity[P, I]`

Doporučení: začít provozní variantou. Evidence Score a RS zachovat ve snapshotu pro auditní obhajobu.

### 4.6 Matematická garance

> `Σ DerivedHours[P, *] = Capacity[P, I]`

Součet odvozených hodin je přesně kapacita osoby na Iteraci, pokud existuje alespoň jeden relevantní item. Platí pro obě varianty výpočtu. Vždy. Bez výjimky.

### 4.7 Dual-view CW: dvě otázky, jeden dataset

Model poskytuje dva komplementární pohledy na stejná data:

| Pohled | Otázka | Výstup | Garance |
|---|---|---|---|
| **Per-person** | Jak se kapacita člověka rozloží mezi jeho items? | Výkaz, OP TAK | Σ = kapacita |
| **Per-item** | Kolik lidí a hodin stál item X? | Nákladová alokace | Σ podílů = 100% |

Per-person normalizace: `DerivedHours[P, item] = (Score[P, item] / Σ Score[P, *]) × Capacity[P, I]`

Per-item normalizace: `ItemShare[P, item] = DerivedHours[P, item] / Σ DerivedHours[*, item]`

Oba pohledy se generují ze stejných dat (CW, JS, Capacity) — žádná duplikace, žádný konflikt.

### 4.8 Příklad: Story S-200 (OMOP parser impl., JS: 8)

**Per-person pohled (každý ze SVÉ kapacity):**

| Kontributor | CW | Score | Jeho ΣScores | Jeho kapacita | Hodiny na S-200 |
|---|---|---|---|---|---|
| **Turyna (Dev, owner)** | 1.0 | 8.0 | 42.3 | 60h | 11.3 h |
| **Tuma (DevSecOps, CI/CD)** | 0.6 | 4.8 | 58.1 | 80h | 6.6 h |
| **Urbánek (Arch, review)** | 0.25 | 2.0 | 28.6 | 40h | 2.8 h |

**Per-item pohled (jak se 20.7h na S-200 rozloží):**

| Kontributor | Hodiny na S-200 | Podíl na itemu |
|---|---|---|
| **Turyna** | 11.3 h | 54.6 % |
| **Tuma** | 6.6 h | 31.9 % |
| **Urbánek** | 2.8 h | 13.5 % |
| **CELKEM** | 20.7 h | 100 % |

---

## 5. Hierarchie work items a WSJF

### 5.1 SAFe 6 mapování

```
Initiative (celý projekt, business case, investiční záměr)
  └── Epic (strategický cíl, 6–9 měsíců, hypothesis + lean BC)
        └── Feature (musí se vejít do Planning Intervalu)
              └── Story (dodáváno v Iteraci)
                    └── Task (technická práce, volitelné)
```

Každá úroveň má vlastní nezávislý Job Size a WSJF. Feature WSJF se nepočítá ze Stories pod ní.

| Úroveň | GitHub mapování | Scope | JS max | WSJF |
|---|---|---|---|---|
| **Initiative** | Top-level issue | Investiční záměr / MVP | — | — |
| **Epic** | Sub-issue pod Initiative | Strategický cíl, 6–9 měs. | 20 | Lokální |
| **Feature** | Sub-issue pod Epic | Musí se vejít do PI | 13 | Lokální |
| **Story** | Sub-issue pod Feature | Dodáváno v Iteraci | 8 (2/10) / 5 (1/5) | Lokální |
| **Task** | Sub-issue / checklist | Technická práce | — | — |

### 5.2 Další Issue Types

- **Risk** — identifikované riziko s mitigací (trackované jako issue)
- **Dependency** — explicitní cross-team závislost
- **Enabler** — technická práce bez přímé business hodnoty (infra, refactoring, research)
- **Bug** — defekt v existující funkcionalitě

### 5.3 WSJF model s Fibonacci řadou

> `WSJF = (BV + TC + RR) / JS`
>
> kde: BV = Business Value, TC = Time Criticality, RR = Risk Reduction, JS = Job Size

Všechny složky používají upravenou Fibonacci řadu: 1, 2, 3, 5, 8, 13, 20. WSJF různých vrstev se navzájem neporovnává.

### 5.4 Postup odhadování (stejná metoda na všech úrovních)

1. Seber všechny položky dané úrovně
2. Pro každou WSJF složku (BV, TC, RR, JS) zvlášť:
   - Najdi nejmenší/nejnižší položku = ta dostane hodnotu 1
   - Každou další položku odhadni relativně vůči nejmenší
   - Použij pouze Fibonacci: 1, 2, 3, 5, 8, 13, 20
3. Vypočti WSJF = (BV + TC + RR) / JS
4. Seřaď sestupně = prioritizovaný backlog

### 5.5 Sizing guardrails per level

| Úroveň | Povolené hodnoty | Warning threshold | Akce |
|---|---|---|---|
| **Story** | 1, 2, 3, 5, 8 | 8 (2/10) nebo 5 (1/5) | Nad limit = rozdělit |
| **Feature** | 3, 5, 8, 13 | 13 | warning:large-feature label |
| **Epic** | 5, 8, 13, 20 | 20 | Split review required |

### 5.6 Traceability chain

> `Initiative -> Epic -> Feature -> Story -> PR -> Commit -> CI/CD -> Deploy`

Každý PR musí referovat work item (S-XXX, F-XXX, E-XXX). Traceability check workflow toto vynucuje.

---

## 6. Epic Hypothesis Statement (SAFe 6)

> *Epic není jen velký pytel práce. Je to investiční hypotéza s governance envelope, business case a měřením úspěšnosti.*

### 6.1 Struktura epicu

Každý epic má 6 sekcí:

- **A. Epic Identity** — ID, typ (Business/Enabler), owner, stakeholders, ART scope
- **B. Epic Hypothesis Statement** — For/Who/The/Is a/That/Unlike/Our solution
- **C. Benefit Hypothesis** — měřitelný přínos s baseline, target, timeframe
- **D. Lean Business Case** — problem, opportunity, strategic alignment, MVP, options, risks
- **E. Governance Envelope** — budget, forecast horizon, WSJF, split review, guardrails
- **F. Delivery Decomposition** — candidate features, dependencies, affected teams

### 6.2 Epic Hypothesis Statement template

> For [cílový zákazník / uživatel / stakeholder]
>
> Who [jaký problém, potřebu nebo omezení dnes mají]
>
> The [název řešení / schopnosti / změny]
>
> Is a [business epic / enabler epic]
>
> That [co to umožní nebo změní]
>
> Unlike [jaký je dnešní stav / alternativa / workaround]
>
> Our solution [v čem je lepší nebo jiná]
>
> Benefit hypothesis: [měřitelný přínos s baseline -> target v timeframe]
>
> Leading indicators: [časné signály správného směru]
>
> Lagging indicators: [finální outcome metriky]

### 6.3 Lean Business Case (light)

- **Problem Statement** — co řešíme
- **Opportunity Statement** — proč teď
- **Strategic Alignment** — OKR / strategie / mandát
- **Expected Business Outcome** — konkrétní hodnota
- **MVP / First Validatable Increment** — nejmenší verze k ověření hypotézy
- **Options Considered** — alternativy + do-nothing option
- **Key Risks and Assumptions**

### 6.4 Kill Criteria

Každý epic (a initiative) musí mít definované kill criteria = podmínky, za kterých se práce zastaví:

- Hypotéza vyvrácena daty
- Budget vyčerpán bez měřitelného progresu
- Externí závislost není splnitelná
- Strategická priorita se změnila

### 6.5 Split Review Decision Framework

Split review je povinný, pokud platí alespoň 2 z následujících triggerů:

- Estimate >= 20 (na hranici Epic maxima)
- Forecast horizon > 2 Planning Intervaly
- Affected ARTs > 1
- Dependencies > 5
- MVP není jasně definované
- Benefit hypothesis je slabě měřitelná
- Confidence = Low

Výsledek split review: Approved as-is / Split into smaller epics / Reclassify as initiative / Hold / Stop

---

## 7. Konfigurace kadence

| Parametr | Varianta A: Klasická (2/10) | Varianta B: AI-Native (1/5) |
|---|---|---|
| **Iterace** | 2 týdny | 1 týden |
| **Planning Interval** | 10 týdnů (4+1 IP) | 5 týdnů (4+1 IP) |
| **Kapacita 1.0 FTE / iter** | 80h | 40h |
| **Kapacita 0.5 FTE / iter** | 40h | 20h |
| **Kapacita 0.25 FTE / iter** | 20h | 10h |
| **Ceremony overhead** | ~3 % | ~6 % |
| **Story max JS** | 8 | 5 |

> *Doporučení: začít na A. Po prvním PI vyhodnotit přechod na B na základě velocity a lead time dat.*

---

## 8. Predictability (3 typy)

### 8.1 Flow Predictability

> `FlowPredictability = DeliveredPoints / PlannedPoints`
>
> `SpilloverRate = SpilloverStories / PlannedStories`

Cíl: FlowPredictability > 0.8, SpilloverRate < 0.15

### 8.2 Outcome Predictability (PI Objectives)

> `ObjectivePredictability = AchievedObjectiveValue / PlannedObjectiveValue`

Každý tým definuje PI Objectives na PI Planningu, mapované na Features s BV. Cíl: > 0.8.

### 8.3 Governance Predictability

Měření disciplíny procesu:

- % items s kompletní traceability (Story -> PR -> merge)
- % items s vyplněným DoR před zahájením
- % items s DoD checklistem splněným před Done
- Počet WIP breaches za sprint/PI

### 8.4 Predictability thresholds

| Metrika | Zelená | Žlutá | Červená |
|---|---|---|---|
| **PI Predictability** | > 0.85 | 0.70–0.85 | < 0.70 |
| **Spillover Rate** | < 0.10 | 0.10–0.20 | > 0.20 |
| **Objective Predictability** | > 0.80 | 0.60–0.80 | < 0.60 |
| **WIP Breaches/sprint** | 0 | 1–2 | > 2 |

---

## 9. WIP limity a flow management

### 9.1 WIP pravidla

| Úroveň | WIP limit | Měření | Akce |
|---|---|---|---|
| **Osoba** | 1 Story (ideál) | In Progress stories per assignee | AI alert + label WIP-VIOLATION |
| **Tým** | = počet členů týmu | In Progress stories per team | Governance alert do Teams |
| **Feature** | 2 per tým | In Progress features per team | PI replanning trigger |
| **Blocked** | > 2 pracovní dny | Doba v Blocked stavu | Eskalace |

### 9.2 Flow metriky (automaticky z GitHubu)

- **Lead Time:** čas od vytvoření Story do Done
- **Cycle Time:** čas od In Progress do Done
- **Throughput:** počet Done stories per sprint
- **WIP Age:** jak dlouho je Story v In Progress
- **Flow Efficiency:** ActiveTime / TotalElapsedTime

---

## 10. Učící smyčka

### 10.1 Velocity tracking

> `Story_Velocity[tým, iterace] = Σ JobSize uzavřených Stories`
>
> `Feature_Velocity[tým, PI] = Σ JobSize uzavřených Features`
>
> `Accuracy = Actual / Planned × 100 %`

### 10.2 CW kalibrace

Po 2–3 Iteracích vyhodnotit: odpovídá heuristika realitě, není PM podhodnocen, není Arch nadhodnocen.

### 10.3 Job Size kalibrace

Referenční Story '3' je jiná než referenční Feature '3'. Každá úroveň se kalibruje nezávisle.

### 10.4 Role AI

AI generuje kód i dokumentaci. Vykazuješ čas na dodání itemu, ne minuty psaní kódu. AI se projeví ve velocity, ne ve výkazech.

---

## 11. Implementace v GitHub

### 11.1 Custom fields

| Field | Typ | Hodnoty / poznámka |
|---|---|---|
| **Issue Type** | Issue type | Initiative, Epic, Feature, Story, Task, Bug, Risk, Dependency, Enabler |
| **Job Size** | Number | Fibonacci 1, 2, 3, 5, 8, 13, 20 |
| **Business Value** | Number | Fibonacci 1–20 |
| **Time Criticality** | Number | Fibonacci 1–20 |
| **Risk Reduction** | Number | Fibonacci 1–20 |
| **WSJF Score** | Number | Auto (Action) |
| **Planning Interval** | Iteration | PI-2026-1, PI-2026-2, ... |
| **Iteration** | Iteration | PI-2026-1.1, PI-2026-1.2, ... |
| **Team** | Single select | ČVUT Dev, Medicalc Dev, DevOps |
| **Primary Owner** | Assignee | Accountable owner |
| **Confidence** | Single select | Low / Medium / High |
| **Objective Link** | Text | OBJ-xx reference (Feature level) |
| **Forecast Horizon** | Text | PI rozsah (Initiative, Epic) |

> *Co nedržet jako GitHub field: Capacity, Derived Hours, FTE, podpisový stav -> patří do evidence vrstvy.*

### 11.2 Workflow statusy per level

| Level | Statusy |
|---|---|
| **Initiative / Epic** | Funnel -> Reviewing -> Approved -> Backlog -> In Progress -> Done -> Stopped |
| **Feature** | Funnel -> Analyzing -> Backlog -> Planned in PI -> Implementing -> Blocked -> Done -> Deferred |
| **Story** | Ready -> In Progress -> Review -> Blocked -> Done |

### 11.3 GitHub Actions (7 workflowů)

| Workflow | Trigger | Co dělá | Output |
|---|---|---|---|
| **1. wsjf-calculator.yml** | Field change (BV/TC/RR/JS) | Auto-výpočet WSJF Score | Comment s WSJF skóre |
| **2. contributor-detector.yml** | PR merge / review / issue | Detekce kontributorů + evidence | Contributor log JSON |
| **3. iteration-close.yml** | Manuální dispatch | Frozen snapshot + MD/JSON/XLSX výkazy + per-item | Výkazy + snapshot |
| **4. pi-close.yml** | Manuální dispatch | Agregace iterací do PI summary | PI summary |
| **5. velocity-tracker.yml** | Iter/PI close | Velocity JSON + dashboard | Velocity data |
| **6. validate-work-item.yml** | issues: opened/edited | Kontrola povinných sekcí dle typu | Label governance:invalid |
| **7. traceability-check.yml** | pull_request: opened | Ověřuje že PR referuje work item | Fail pokud chybí |

### 11.4 governance/config.yml (centrální konfigurace)

```yaml
projects:
  delivery: 1          # hlavní projekt (Portfolio + Team)
  governance: 2        # governance / flow views

sizing:
  epic: [5, 8, 13, 20]
  feature: [3, 5, 8, 13]
  story_2w: [1, 2, 3, 5, 8]
  story_1w: [1, 2, 3, 5]

thresholds:
  epic_split_review: 20
  feature_warning: 13
  story_warning_2w: 8
  story_warning_1w: 5
  blocked_days_alert: 2
  pi_predictability_warning: 0.8
  spillover_warning: 0.15

edpa:
  evidence_threshold: 1.0
  cw_min: 0.15
  cw_max: 1.0
  mode: simple         # simple | full
```

### 11.5 Governance Label System

| Label | Kategorie | Význam |
|---|---|---|
| **governance:invalid** | Validation | Chybí povinné sekce v issue body |
| **split-review:required** | Epic governance | Epic na hranici sizing guardrails |
| **warning:large-story** | Sizing | Story na/nad warning threshold |
| **warning:large-feature** | Sizing | Feature na/nad warning threshold |
| **dor:passed** | Quality gate | Definition of Ready splněna |
| **dod:passed** | Quality gate | Definition of Done splněna |
| **traceability:ok** | Traceability | PR reference existuje |
| **WIP-VIOLATION** | Flow | Osoba/tým překročila WIP limit |
| **edpa:contributor** | EDPA | Osoba detekována jako kontributor |

### 11.6 Branch naming & PR template

```
feature/S-200-omop-parser
bugfix/S-215-upload-validation
feature/F-102-anon-engine
```

CI check blokuje PR bez reference na issue (S-XXX, F-XXX, E-XXX).

PR Template obsahuje: Linked work item (#číslo), Change type, Evidence checklist (testy, AC, docs).

---

## 12. Governance Readiness Gates

### 12.1 Initiative Ready

- Problem/opportunity defined
- Strategic alignment confirmed
- Budget envelope set
- Expected outcomes measurable
- Candidate epics identified
- Kill criteria defined

### 12.2 Epic Ready for Portfolio Backlog

- Hypothesis statement complete (For/Who/The/That/Unlike)
- Measurable benefit hypothesis s baseline a target
- MVP / first validatable increment defined
- Budget envelope set
- Forecast horizon defined
- WSJF inputs filled (BV, TC, RR, JS)
- Epic Owner assigned
- First feature decomposition
- Dependencies and risks identified
- Split review done (if required)

### 12.3 Feature Ready for PI

- Parent epic linked
- Feature statement with acceptance criteria
- Benefit hypothesis
- Target PI assigned
- PI Objective linked
- Estimate within allowed range (3–13)
- Owning team assigned
- Dependencies identified

### 12.4 Story Ready for Sprint (DoR)

- Clear description (As a / I want / So that)
- Clear acceptance criteria
- Estimate within allowed range (1–8 nebo 1–5 dle kadence)
- Dependencies identified
- Small enough for sprint
- Team understands scope
- Parent feature linked

### 12.5 Story Done (DoD)

- Implementation complete
- Code reviewed (PR approved)
- Tests passed (CI zelené)
- Linked PR exists and merged
- Documentation updated if needed
- Deployed or ready for release
- Acceptance confirmed

---

## 13. AI Snapshot Layer

AI Snapshot Layer nahrazuje tradiční BI nástroje (Power BI, Grafana). Místo dashboardů generuje AI interpretované reporty z dat.

### 13.1 Pipeline

1. `snapshot-generator.yml` (pondělí 6:00) -> `snapshots/weekly/latest.json`
2. AI model interpretuje JSON -> generuje Markdown report
3. Report commitnut do `ai-insights/` adresáře
4. Teams notifikace s linkem

### 13.2 AI report režimy

- **Executive:** 5 bullet summary, budget status, key risks, strategic progress
- **ART (RTE):** PI progress, dependencies, cross-team issues, predictability score
- **Team Lead:** sprint velocity, WIP, individual load, blockers, spillover risk
- **Finance:** FTE využití, EDPA derived hours, nákladová alokace per deliverable
- **Governance:** compliance score, DoD violations, traceability gaps, audit trail

### 13.3 Snapshot JSON struktura (příklad)

```json
{
  "date": "2026-05-19",
  "portfolio": {
    "initiatives": 1,
    "epics_active": 3,
    "epics_split_review": 0
  },
  "pi": {
    "id": "PI-2026-1",
    "planned_feature_points": 60,
    "delivered_feature_points": 47,
    "predictability": 0.78
  },
  "team": {
    "velocity_avg": 24,
    "capacity_hours": 380,
    "wip_breaches": 1,
    "blocked_items": 2
  },
  "edpa": {
    "mode": "simple",
    "persons_computed": 8,
    "iterations_closed": 3,
    "total_derived_hours": 1140
  },
  "flow": {
    "stories_done": 18,
    "stories_spillover": 2
  }
}
```

---

## 14. Výkazy a audit

### 14.1 Reporting pipeline

```
/snapshots/
  iteration-PI-2026-1.3.json        <- frozen snapshot

/reports/
  iteration-PI-2026-1.3/
    vykaz-urbanek.md                 <- čitelný výkaz
    vykaz-urbanek.json               <- strojová data
    summary.xlsx                     <- souhrnný Excel
    item-costs.xlsx                  <- per-item pohled

/signed/
  PI-2026-1.3-urbanek.pdf           <- BankID podepsaný
```

### 14.2 Freeze rule

> *Po Iteration Close: snapshot je frozen. Evidence se nepřepisuje in-place. Každá oprava je nová revize. Zásadní pro auditní obhajobu.*

### 14.3 Auditní princip

Průkaznost stojí na 5 pilířích:

- GitHub delivery evidence (commity, PR, reviews, comments)
- Capacity registry (YAML config v repo)
- Frozen snapshot (reprodukovatelný vstup)
- Reprodukovatelný výpočet (Score = JS × CW × RS)
- Podepsaný výstup (BankID, zákon 21/2020 Sb.)

---

## 15. Tým projektu

| Jméno | Role | Tým | FTE | h/iter (2t) | h/PI | Účet |
|---|---|---|---|---|---|---|
| **J. Urbánek** | Arch | ČVUT | 0.5 | 40h | 200h | urbanek@ |
| **O. Tůma** | DevSecOps | ČVUT | 1.0 | 80h | 400h | tuma@ |
| **Turyna** | Dev | ČVUT | 0.75 | 60h | 300h | @cvut.cz |
| **Matoušek** | Dev | ČVUT | 0.75 | 60h | 300h | @cvut.cz |
| **PM Medicalc** | PM | MC | 0.5 | 40h | 200h | pm@ |
| **Sr Dev MC** | Dev | MC | 0.5 | 40h | 200h | @medicalc.cz |
| **DB Spec MC** | Dev | MC | 0.5 | 40h | 200h | @medicalc.cz |
| **DevOps MC** | Dev | MC | 0.25 | 20h | 100h | @medicalc.cz |
| **CELKEM** | | | **4.75** | **380h** | **1 900h** | |

---

## 16. Srovnání s alternativami

| Vlastnost | Fixed Split v1 | EDPA 1.0.0-beta (tento model) | Ruční timesheets |
|---|---|---|---|
| **Předem fixované koše** | Ano | Ne | Ne |
| **Prázdné úrovně** | Problém | Neexistují | N/A |
| **Per-person pohled** | Ano | Ano (primární) | Ano |
| **Per-item pohled** | Ne | Ano (dual-view) | Ne |
| **Cross-funkční spolupráce** | Omezená | Plná | Plná |
| **Automatizace** | Střední | Vysoká | Žádná |
| **Matematická garance** | Složitější | Nativně | Ne |
| **SAFe governance** | Ne | Ano (Epic Hypothesis, WSJF) | Ne |
| **AI reporting** | Ne | Ano (Snapshot Layer) | Ne |

---

## 17. Rizika a mitigace

| Riziko | Dopad | Mitigace |
|---|---|---|
| **Auditor neuzná EDPA model** | Vysoký | Formální metodika, frozen snapshoty, reprodukovatelnost, BankID podpis |
| **CW heuristika neodpovídá realitě** | Střední | Manuální override + kalibrace po 2–3 iteracích |
| **ČVUT IT odmítne B2B Direct Connect** | Střední | Guest přístup funguje bez spolupráce IT (horší UX) |
| **Commit bez S-/F-/E-XXX reference** | Střední | CI check blokuje PR, traceability-check.yml |
| **PM/Arch práce bez commitů** | Střední | Issue comments + /contribute příkaz |
| **0 relevantních items pro osobu** | Nízký | Procesní eskalace, ne matematická improvizace |
| **Týmy nejsou disciplinované** | Střední | Governance labels + WIP alerty + soft enforcement |
| **WSJF gaming (manipulace odhadů)** | Střední | Cross-team kalibrace + AI detekce anomálií |
| **Body použity jako KPI lidí** | Vysoký | Explicitní pravidlo: body NEJSOU KPI jednotlivců |

---

## 18. Implementační plán

| # | Akce | Čas | Popis |
|---|---|---|---|
| **1** | Doména kashealth.cz (WEDOS) | 10 min | Registrace, DNS propagace na pozadí |
| **2** | M365 tenant + 5 licencí | 2h | Tenant, doména, licence, guest konfig, Teams |
| **3** | GitHub org + Team plan | 1h | Organizace, upgrade, pozvánky, branch protection |
| **4** | GitHub Projects + custom fields | 2h | Issue types, hierarchie, fields, views, iterations |
| **5** | Actions 1–2 (WSJF + Contributor) | 3 dny | WSJF Calculator + Contributor Detector |
| **6** | Actions 3–5 (Close + Velocity) | 2 dny | Iteration Close + PI Close + Velocity Tracker |
| **7** | Actions 6–7 (Validate + Traceability) | 1 den | Validate work item + Traceability check |
| **8** | governance/config.yml + labels | 0.5 dne | Centrální konfigurace + label system |
| **9** | Issue Forms YAML (4 formuláře) | 1 den | Initiative, Epic, Feature, Story templates |
| **10** | Pilotní iterace + kalibrace | 1–2t | První výkazy, kalibrace CW, end-to-end test |
| **11** | AI Snapshot Layer (volitelně) | 2 dny | snapshot-generator + AI report + ai-insights |
| **12** | Retro po 1. PI | 1 den | Kadence, CW accuracy, velocity, dual-view validace |

---

## 19. Závěr

> *Člověk deklaruje kapacitu za období. Systém identifikuje work items, na kterých se prokazatelně podílel. Kapacita se rozpadne poměrně podle Job Size a contribution relevance.*

**Jádro modelu:**

> `Derived Time = Capacity × poměr score work itemu vůči celku`
>
> `Score = Job Size × Contribution Weight × Relevance Signal`
>
> Bez LevelFactoru. Bez timesheetů. Bez fixovaných košů.

**Dva komplementární pohledy:**

- **Per-person:** Σ DerivedHours[P, *] = Capacity[P, I] -> výkazy pro OP TAK
- **Per-item:** Σ DerivedHours[*, item] = celková investice do itemu -> nákladová alokace

**Governance framework:**

- SAFe 6 inspired: Epic Hypothesis Statement, Lean Business Case, Kill Criteria
- 3 typy Predictability: Flow, Outcome, Governance
- 7 GitHub Actions s centrální konfigurací (governance/config.yml)
- Governance Readiness Gates: DoR/DoD per úroveň
- AI Snapshot Layer: JSON -> AI -> Markdown reporty

> *Minimální investice (~1 520 Kč/měs.) pro centrální řízení, automatizovaný workflow, evidence-driven vykazování, SAFe 6 governance, nezávislost na externích IT odděleních a přípravu na spin-off bez budoucí migrace.*
