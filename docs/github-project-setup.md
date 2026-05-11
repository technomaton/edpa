# GitHub Project Setup — Inicializace EDPA projektu

## Přehled

EDPA používá GitHub Projects v2 jako vizuální vrstvu pro správu backlogu. Tento dokument popisuje kompletní postup inicializace nového projektu — od prerekvizit po synchronizaci s Git-native backlogem.

```
GitHub Projects (UI)          Git repo (.edpa/backlog/)
       │                             │
       │  ┌─────────────────────┐    │
       ├──│  sync.py pull       │──→ │  Projects → .edpa/backlog/
       │  └─────────────────────┘    │
       │  ┌─────────────────────┐    │
       │←─│  sync.py push       │──┤ │  .edpa/backlog/ → Projects
       │  └─────────────────────┘    │
```

## 1. Prerekvizity

### GitHub CLI s project scope

```bash
gh auth refresh -s project,read:project
```

Ověření:

```bash
gh auth status  # mělo by ukazovat 'project' scope
```

### Backlog soubor

`.edpa/backlog/` musí existovat s hierarchií work items (per-item YAML files) (Initiative → Epic → Feature → Story). Viz [backlog format](#backlog-format) níže.

### Python

```bash
python --version  # 3.10+
pip install pyyaml
```

## 2. Automatizovaný setup

Jeden příkaz vytvoří kompletní GitHub Project:

```bash
python .claude/edpa/scripts/project_setup.py \
  --org <GITHUB_ORG> \
  --repo <REPO_NAME> \
  --project-title "EDPA — Název projektu"
```

### Příklad

```bash
python .claude/edpa/scripts/project_setup.py \
  --org technomaton \
  --repo edpa-simulation \
  --project-title "EDPA Simulation — Medical Platform"
```

### Co skript udělá (9 kroků)

| Krok | Akce | Detail |
|------|------|--------|
| **[1]** | Ověří Issue Types | Native GitHub Issue Types (org-level): Initiative, Epic, Feature, Story, Defect, Task — vytvořeny přes `issue_types.py setup` |
| **[2]** | Vytvoří GitHub Project | Projects v2 na org úrovni |
| **[3]** | Vytvoří custom fields | Job Size, Business Value, Time Criticality, Risk Reduction, WSJF Score (NUMBER), Team (SINGLE_SELECT), 4 Status fields (Initiative/Epic/Feature/Story Status with SAFe workflow options) |
| **[4]** | Linkuje projekt k repo | Projekt viditelný v repo Projects tabu |
| **[5]** | Dotáže Issue Types | Native Issue Types z organizace (Initiative, Epic, Feature, Story, Defect, Task) |
| **[6]** | Vytvoří issues | Ze `.edpa/backlog/`, s Issue Types podle úrovně |
| **[7]** | Nastaví field values | JS, BV, TC, RR, WSJF, Status na všech project items |
| **[8]** | Propojí sub-issues | Parent-child hierarchie (Initiative→Epic→Feature→Story) přes GitHub Sub-issues API |
| **[9]** | Aktualizuje config | `.edpa/config/edpa.yaml` — uloží project number a ID pro sync |

### Dry-run

```bash
python .claude/edpa/scripts/project_setup.py \
  --org technomaton --repo edpa-simulation --dry-run
```

Zobrazí plán bez provedení.

## 3. Manuální krok — view layout

> **GitHub Projects v2 API neumožňuje konfigurovat viditelné sloupce v tabulkovém view programaticky.** Toto je jediný manuální krok.

1. Otevřít projekt v prohlížeči: `https://github.com/orgs/<ORG>/projects/<NUMBER>`
2. V table view kliknout na **+** tlačítko vpravo v headeru (vedle posledního sloupce)
3. Přidat sloupce:
   - **Issue Type** — typ položky (Initiative/Epic/Feature/Story)
   - **Job Size** — relativní velikost (Fibonacci 1-20)
   - **Business Value** — business hodnota
   - **Time Criticality** — časová kritičnost
   - **Risk Reduction** — redukce rizika
   - **WSJF Score** — prioritizační skóre = (BV + TC + RR) / JS
   - **Team** — přiřazený tým

4. Volitelně: vytvořit Board view (seskupení podle Status)
5. Volitelně: vytvořit Roadmap view (seskupení podle Iteration)

## 4. Synchronizace

### GitHub Projects → Git (pull)

```bash
python .claude/edpa/scripts/sync.py pull
```

Stáhne aktuální stav z GitHub Projects a aktualizuje `.edpa/backlog/`. Změny zaloguje do `.edpa/changelog.jsonl`.

### Git → GitHub Projects (push)

```bash
python .claude/edpa/scripts/sync.py push
```

Pošle změny z `.edpa/backlog/` do GitHub Projects.

### Diff (co se změní)

```bash
python .claude/edpa/scripts/sync.py diff
```

Dry-run — ukáže rozdíly bez provedení.

### Stav synchronizace

```bash
python .claude/edpa/scripts/sync.py status
```

### Automatická synchronizace (GitHub Actions)

Dvě Actions zajišťují automatický sync:

| Workflow | Trigger | Směr |
|----------|---------|------|
| `edpa-sync-projects-to-git.yml` | Cron každých 15 minut | Projects → `.edpa/backlog/` |
| `edpa-sync-git-to-projects.yml` | Push na `.edpa/backlog/` | `.edpa/backlog/` → Projects |

Loop prevention: commity od `github-actions[bot]` netriggerují reverse sync.

## 5. Backlog format

`.edpa/backlog/` — kompletní hierarchie v YAML:

```yaml
project:
  name: "Název projektu"
  registration: "CZ.01.01.01/01/24_062/0007440"
  program: "OP TAK"

initiatives:
  - id: I-1
    title: "Název initiative"
    status: Implementing
    epics:
      - id: E-10
        title: "Název epicu"
        type: Business          # Business | Enabler
        js: 13
        bv: 13
        tc: 8
        rr: 8
        wsjf: 2.23              # = (bv + tc + rr) / js
        status: Implementing
        owner: urbanek
        epic_hypothesis:
          for: "cílový zákazník"
          who: "jaký problém mají"
          the: "název řešení"
          is_a: "Business Epic"
          that: "co to umožní"
          unlike: "současný stav"
          our_solution: "v čem je lepší"
          benefit_hypothesis:
            metric: "co měříme"
            baseline: "současný stav"
            target: "cílový stav"
            timeframe: "do kdy"
          kill_criteria:
            - "podmínka pro zastavení"
        features:
          - id: F-100
            title: "Název feature"
            js: 8
            status: Done
            stories:
              - id: S-200
                title: "Název story"
                js: 8
                status: Done
                assignee: turyna
                iteration: PI-2026-1.1
                contributors:
                  - person: turyna
                    cw: 1.0
                    contribution_score: 4.0
                    signals:
                      - type: assignee
                        ref: issue#137
                        weight: 4.0
```

## 6. Backlog CLI

```bash
python .claude/edpa/scripts/backlog.py tree                    # Celá hierarchie
python .claude/edpa/scripts/backlog.py show E-10               # Detail položky + hypotéza
python .claude/edpa/scripts/backlog.py wsjf                    # WSJF prioritizace
python .claude/edpa/scripts/backlog.py status                  # Stav projektu
python .claude/edpa/scripts/backlog.py validate                # Kontrola integrity
```

## 7. Kompletní flow — od nuly po běžící projekt

```
1. Nainstalovat EDPA plugin
   curl -fsSL https://edpa.technomaton.com/install.sh | sh

2. Inicializovat EDPA
   /edpa setup "Project Name"
   
   
   

3. Naplnit backlog
   # Editovat .edpa/backlog/ — definovat epicy, features, stories (per-item files)
   python .claude/edpa/scripts/backlog.py validate

4. Setup GitHub Project
   python .claude/edpa/scripts/project_setup.py --org ORG --repo REPO

5. Manuálně přidat sloupce v GitHub UI (viz krok 3 výše)

6. Začít pracovat
   # Tým pracuje v GitHub Projects (Board view)
   # Sync automaticky verzuje změny do .edpa/backlog/
   # Na konci iterace: python .claude/edpa/scripts/engine.py --iteration PI-YYYY-N.I
```

## Reference

- [EDPA metodika](methodology.md)
- [Auto-kalibrace](auto-calibration.md)
- [Evidence detection](evidence-detection.md)
- [Audit trail](audit-trail.md)
- [Simulace](https://github.com/technomaton/edpa-simulation)
- [Web](https://edpa.technomaton.com)
