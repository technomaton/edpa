# EDPA — Evidence-Driven Proportional Allocation

*Capacity derivation from delivery evidence*

**Version 1.0.0-beta — March 2026 — Jaroslav Urbanek, Lead Architect**

---

## 1. Summary

Time is not measured — it is derived. Nobody logs hours. Nobody fills timesheets.

A person declares capacity for a period. The system identifies work items they demonstrably contributed to. Capacity is proportionally distributed ex post among relevant items based on Job Size and contribution weight.

The result is a timesheet that is a byproduct of delivery, not a separate administrative activity.

The model provides two complementary views of the same data:

- **Per-person view**: how a person's capacity distributes across their items → timesheets
- **Per-item view**: how work on an item distributes across people → cost allocation, audit per deliverable

---

## 2. Terminology

| Term | Definition | Configuration |
|---|---|---|
| **Iteration** | Delivery cycle. Stories are planned, delivered, and closed. | 1 week (AI-native) or 2 weeks (classic) |
| **Planning Interval (PI)** | Planning cycle. Features are planned, coordinated, and evaluated. | 5 weeks (4+1 IP) or 10 weeks (8+2 IP) |
| **IP Iteration** | Innovation & Planning iteration at the end of PI. | Last iteration in PI |
| **Job Size (JS)** | Relative size estimate. Modified Fibonacci: 1, 2, 3, 5, 8, 13, 20. | Independent per level |
| **WSJF** | Prioritization score: (BV + TC + RR) / Job Size | Independent per level |
| **Contribution Weight (CW)** | Person's involvement level on a work item. Independent per person. | 0.15–1.0, from evidence or manual override |
| **Evidence Score** | Raw sum of activity signals for a person on an item from GitHub data. Detection layer. | Automatic |
| **Relevance Signal (RS)** | Normalized relevance signal derived from Evidence Score. Mathematical input. | Automatic |
| **Derived Hours** | Derived hours, model output. | Automatic after Iteration Close |

---

## 3. Model Architecture

### 3.1 Three Separate Layers

| Layer | Purpose | Where it lives |
|---|---|---|
| **Operational Metadata Layer** | Live delivery data | GitHub Issues + GitHub Projects |
| **Capacity Registry Layer** | People's capacity, roles, FTE, availability | YAML/JSON config in repo |
| **Evidence & Reporting Layer** | Frozen snapshots, timesheets, Excel, signatures | `.edpa/snapshots`, `.edpa/reports`, `.edpa/reports/signed` |

### 3.2 GitHub as Source of Truth

**GitHub IS source of truth for:** issue hierarchy, ownership, work status, PI/Iteration assignment, Job Size, WSJF inputs, review and merge trail, delivery audit trail.

**GitHub is NOT primary source of truth for:** hourly capacity, FTE records, derived hours for closed periods, signature status. These live in the Evidence & Reporting layer.

---

## 4. Work Item Hierarchy

```text
Initiative (entire project, business case)
  └── Epic (strategic goal, 6–9 months)
       └── Feature (must fit within a Planning Interval)
            └── Story (delivered in an Iteration)
                 └── Task (technical work, optional)
```

Each level has its own independent Job Size and WSJF. Feature WSJF is not calculated from Stories beneath it.

Granularity rules: Story max 8 SP (2/10) or 5 SP (1/5), Feature max 13, Epic max 20. Over limit → break down.

---

## 5. The Model: Evidence-Driven Proportional Allocation

### 5.1 Iteration Planning Protocol

Before EDPA derives hours (ex-post), the team must plan the iteration (ex-ante). Planning requires confirmed capacity as input.

**Step 1 — Confirm Capacity.** Each team member confirms availability for the iteration. This is a commitment, not an estimate. External collaborators negotiate allocation explicitly. Result: `Capacity[P, I]` in `.edpa/config/people.yaml` with `availability: confirmed`.

**Step 2 — Calculate Planning Capacity.**

```text
Team_Total_Capacity = Σ Capacity[P, I]
Team_Planning_Capacity = Team_Total_Capacity × planning_factor (default 0.8)
```

The `planning_factor` is a **team-level** property (configured per team in `.edpa/config/people.yaml` under `teams:`). Different teams may choose different factors based on their support load, maturity, and risk tolerance. It reserves a buffer for support, maintenance, incidents, and unplanned work.

**Step 3 — Select Work.** Pull stories from the prioritized backlog (WSJF order) until `Σ JobSize` approaches historical velocity scaled by `planning_factor`. Do not plan to 100% of capacity.

**Step 4 — Buffer.** The remaining ~20% absorbs unplanned work. If buffer items generate delivery evidence (commits, PRs, reviews), EDPA allocates them normally — the model is unchanged.

**Step 5 — Edge case.** If no unplanned work occurs, all capacity is allocated to planned items. The mathematical guarantee (`Σ DerivedHours = Capacity`) holds regardless.

**Why plan to 80%?** Planning to 100% capacity forces the team into one of three failure modes: undelivered stories (velocity miss), overwork, or scope creep. The 80% heuristic is consistent with SAFe load factor, Scrum velocity-based planning, and Kanban WIP limits.

### 5.2 Inputs

For person **P** and Iteration **I**:

| Input | Source | Example |
|---|---|---|
| `Capacity[P, I]` | Confirmed at Iteration Planning | 40h |
| `RelevantItems[P, I]` | Automatically from GitHub evidence | 6 items across 3 levels |
| `JobSize[item]` | Custom field on issue | Fibonacci 1–20 |
| `ContributionWeight[P, item]` | From evidence / manual override | 0.15–1.0 |
| `RelevanceSignal[P, item]` | Normalized from Evidence Score | 0.25–1.0 |

### 5.3 Evidence Detection

| GitHub signal | Evidence score | Typical CW |
|---|---:|---:|
| Assignee on issue | +4 | 1.0 |
| Explicit `/contribute` command | +3 | 0.6 |
| PR author referencing item | +2 | 0.6 |
| Commit author with S-XXX / F-XXX / E-XXX in message | +1 | 0.25 |
| PR reviewer on PR referencing item | +1 | 0.25 |
| Issue / PR comment in design discussion | +0.5 | 0.15 |

Rules:
- Relevance threshold: Evidence Score >= 1.0
- CW heuristic: strongest signal determines default CW
- Manual override: `/contribute @person weight:0.6`
- Commit count does NOT convert to time — only signals relevance

### 5.4 Calculation — Two Variants

**Methodologically pure variant (audit):**
```text
Score[P, item] = JobSize[item] x ContributionWeight[P, item] x RelevanceSignal[P, item]
DerivedHours[P, item] = (Score[P, item] / SumScores[P, I]) x Capacity[P, I]
```

**Simplified operational variant:**
```text
Score[P, item] = JobSize[item] x ContributionWeight[P, item]
DerivedHours[P, item] = (Score[P, item] / SumScores[P, I]) x Capacity[P, I]
```

Recommendation: start with operational variant. Preserve Evidence Score and Relevance Signal in snapshots for audit defense.

### 5.5 Mathematical Guarantee

```text
Σ DerivedHours[P, item] = Capacity[P, I]
```

Sum of derived hours equals exactly the person's capacity for the Iteration, provided at least one relevant item exists. Holds for both calculation variants.

---

## 6. Dual-View CW: Two Questions, One Dataset

### 6.1 The Problem

CW = 0.25 for a reviewer on a Story can mean two things:

- **Per-person view:** "this item took 25% of attention vs their other items" → capacity distribution
- **Per-item view:** "they did 25% of the work on this item" → cost allocation per deliverable

These are two different questions. One set of CWs cannot cover both. The model solves both — from the same data, with two normalizations.

### 6.2 Per-Person Normalization (Timesheets)

Answers: **How does person P's capacity distribute across their items?**

```text
DerivedHours[P, item] = (Score[P, item] / Σ Score[P, *]) x Capacity[P, I]

Guarantee: Σ DerivedHours[P, *] = Capacity[P, I]
```

Output: **timesheet per person** — how many hours P spent on which item.

### 6.3 Per-Item Normalization (Cost Allocation)

Answers: **How does work on item X distribute across people?**

```text
ItemShare[P, item] = DerivedHours[P, item] / Σ DerivedHours[*, item]

Where Σ runs over all contributors of the item.
```

Output: **cost card per item** — how many hours each person invested in this deliverable.

### 6.4 Example: Story S-200 (OMOP parser impl., JS: 8)

**Per-person view** (each from THEIR capacity):

| Contributor | CW | Score | Their ΣScores | Their capacity | Hours on S-200 |
|---|---:|---:|---:|---:|---:|
| Turyna (Dev, owner) | 1.0 | 8.0 | 42.3 | 60h | 11.3h |
| Tuma (DevSecOps, CI/CD) | 0.6 | 4.8 | 58.1 | 80h | 6.6h |
| Urbanek (Arch, review) | 0.25 | 2.0 | 28.6 | 40h | 2.8h |

**Per-item view** (how 20.7h on S-200 distributes):

| Contributor | Hours on S-200 | Share of item |
|---|---:|---:|
| Turyna | 11.3h | 54.6% |
| Tuma | 6.6h | 31.9% |
| Urbanek | 2.8h | 13.5% |
| **Total** | **20.7h** | **100%** |

### 6.5 When to Use Which

| View | Question | Output | Guarantee |
|---|---|---|---|
| Per-person | How many hours did P spend on what? | Timesheet, OP TAK | Σ = capacity |
| Per-item | How many people and hours did item X cost? | Cost allocation, audit per deliverable | Σ shares = 100% |

Both views are generated from the same data (CW, JS, Capacity) — no duplication, no conflict.

---

## 7. Cadence Configuration

### Variant A: Classic (2/10)

| Cycle | Duration | Capacity 1.0 FTE | 0.5 FTE | 0.25 FTE |
|---|---|---:|---:|---:|
| Iteration | 2 weeks | 80h | 40h | 20h |
| Planning Interval | 10 weeks (4+1 IP) | 400h | 200h | 100h |

### Variant B: AI-Native (1/5)

| Cycle | Duration | Capacity 1.0 FTE | 0.5 FTE | 0.25 FTE |
|---|---|---:|---:|---:|
| Iteration | 1 week | 40h | 20h | 10h |
| Planning Interval | 5 weeks (4+1 IP) | 200h | 100h | 50h |

Recommendation: start on A, evaluate switch to B after first PI based on data.

---

## 8. Learning Loop

### 8.1 Velocity Tracking
```text
Story_Velocity[team, iteration] = Σ JobSize of closed Stories
Feature_Velocity[team, PI] = Σ JobSize of closed Features
Accuracy = Actual / Planned x 100%

Planned_Velocity = Σ JobSize of planned Stories (selected at Iteration Planning)
Actual_Velocity = Σ JobSize of all closed Stories (planned + unplanned)
Buffer_Usage = unplanned hours / (Total_Capacity - Planning_Capacity) x 100%
```

Buffer_Usage tracks how much of the 20% reserve was consumed by unplanned work. Consistently high buffer usage (>90%) suggests raising capacity or reducing planned scope. Consistently low usage (<30%) suggests the team can plan closer to capacity.

### 8.2 CW Calibration
After 2–3 Iterations evaluate: does the heuristic match reality?

### 8.3 Job Size Calibration
Reference Story "3" is different from reference Feature "3". Each level calibrates independently.

### 8.4 Role of AI
AI generates code and documentation. You report time for delivering an item, not minutes writing code. AI shows up in velocity, not in timesheets.

### 8.5 Auto-Calibration of CW Heuristics (after 1st PI)

After the first Planning Interval, sufficient ground truth exists: manually confirmed CW from 4–5 closed iterations. From this point, CW heuristics can be automatically calibrated using an optimization loop inspired by Karpathy's autoresearch pattern.

Principle: one file, one metric, one loop.

```text
Target:     .edpa/config/heuristics.yaml
Metric:     mean_absolute_deviation (auto CW vs ground truth)
Direction:  lower
Eval:       python .claude/edpa/scripts/evaluate_cw.py --ground-truth last_pi
Budget:     50–100 experiments, ~2h overnight
Memory:     git log on calibration branch
```

Safety constraint: agent must NOT edit .claude/edpa/scripts/evaluate_cw.py (evaluator). Separation of optimizer from objective function prevents gaming.

When to activate: earliest after 1st PI (10 weeks), when >= 20 manually confirmed CW records exist.

Expected benefit: more accurate CW without manual retrospective discussion, 15–30% deviation reduction vs static heuristic.

---

## 9. GitHub Implementation

### 9.1 Custom Fields

| Field | Type | Values |
|---|---|---|
| Issue Type | Issue type | Initiative, Epic, Feature, Story, Task, Bug |
| Job Size | Number | Fibonacci 1–20 |
| Business Value | Number | Fibonacci 1–20 |
| Time Criticality | Number | Fibonacci 1–20 |
| Risk Reduction | Number | Fibonacci 1–20 |
| WSJF Score | Number | Auto |
| Planning Interval | Iteration | 5 or 10 weeks |
| Iteration | Iteration | 1 or 2 weeks |
| Team | Single select | Team values |
| Primary Owner | Assignee | Accountable owner |
| Confidence | Single select | Low / Medium / High |

Do not store as GitHub field: Iteration Capacity, Derived Hours, FTE, signature status.

### 9.2 GitHub Actions

| # | Action | Trigger | Function |
|---|---|---|---|
| 1 | WSJF Calculator | Field change (BV/TC/RR/JS) | Auto-calculate WSJF |
| 2 | Contributor Detector | PR merge, review, issue activity | Detect contributors and evidence |
| 3 | Iteration Close | Manual dispatch | Snapshot + timesheets (MD/JSON/XLSX) + per-item allocation |
| 4 | PI Close | Manual dispatch | Iteration aggregation |
| 5 | Velocity Tracker | Iteration/PI close | Velocity JSON + dashboard |

### 9.3 Branch Naming
```text
feature/S-200-omop-parser
bugfix/S-215-upload-validation
feature/F-102-anon-engine
```
CI check blocks PRs without issue reference (S-XXX, F-XXX, E-XXX).

### 9.4 Definition of Ready
No item enters delivery without: Issue Type, Parent, Job Size, BV+TC+RR, Owner. Contributor is required no later than entry into actual delivery evidence.

---

## 10. Timesheets and Audit

### 10.1 Pipeline
```text
Iteration Close → per person:
  .edpa/reports/iteration-{I}/vykaz-{person}.md
  .edpa/reports/iteration-{I}/vykaz-{person}.json
  .edpa/reports/iteration-{I}/summary.xlsx
  .edpa/reports/iteration-{I}/item-costs.xlsx    ← per-item view

PI Close → aggregation:
  .edpa/reports/planning-interval-{PI}/summary.xlsx

Annual:
  .edpa/reports/2026/annual.xlsx
```

### 10.2 Freeze Rule
After Iteration Close: snapshot is created, frozen, evidence is never overwritten in-place, every correction is a new revision. Critical for audit defense.

### 10.3 Audit Principle
Auditability rests on: GitHub delivery evidence + capacity registry + frozen snapshot + reproducible calculation + signed output (BankID).

---

## 11. Assumptions and Risks

| Assumption | Detail |
|---|---|
| All items are closed | Undelivered items are moved, not deleted |
| Capacity confirmed at Iteration Planning | Each member confirms availability |
| Branch naming followed | CI check enforces S-/F-/E-XXX |
| Job Size consistent per level | Planning Poker, reference items |
| CW calibrated after first Iterations | Retrospective evaluates heuristic |

| Risk | Impact | Mitigation |
|---|---|---|
| Auditor rejects model | High | Methodology, frozen snapshots, reproducibility, BankID |
| CW heuristic doesn't match | Medium | Override + calibration |
| Commit without S-/F-/E-XXX | Medium | CI check blocks PR |
| PM/Arch work without commits | Medium | Comments + /contribute |
| 0 relevant items | Low | Process escalation |

---

## 12. Comparison with Alternatives

| Property | Fixed Split v1 | Evidence-Driven 1.0 | Manual Timesheets |
|---|---|---|---|
| Pre-fixed buckets | Yes | No | No |
| Empty levels | Problem | Don't exist | N/A |
| Per-person view | Yes | Yes (primary) | Yes |
| Per-item view | No | Yes (dual-view) | No |
| Cross-functional collaboration | Limited | Full | Full |
| Automation | Medium | High | None |
| Mathematical guarantee | Complex | Native | No |

---

## 13. Conclusion

The final methodology rests on the principle:

> **A person declares capacity for a period.**
> **The system identifies work items they demonstrably contributed to.**
> **Capacity is proportionally distributed by Job Size and contribution relevance.**

Core model:

> **Derived Time = Capacity x score ratio of work item to total**
> **Score = Job Size x Contribution Weight x Relevance Signal**

Two complementary views:

> **Per-person:** Σ DerivedHours[P, *] = Capacity[P, I] → timesheets
> **Per-item:** Σ DerivedHours[*, item] = total investment in item → cost allocation
