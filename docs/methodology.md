# EDPA — Evidence-Driven Proportional Allocation

*Capacity derivation from delivery evidence*

**Version 2.5.0 — June 2026 — Jaroslav Urbanek, Lead Architect**

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

### 3.2 Source of Truth (V2)

**Git + YAML IS source of truth for:** backlog item hierarchy, ownership, work status, PI/Iteration assignment, Job Size, WSJF inputs, delivery audit trail. Everything lives in `.edpa/backlog/**/*.md` (YAML frontmatter) and `.edpa/iterations/*.yaml`.

**GitHub is optional:** PR/commit/review events are additional delivery evidence — they flow in via the contribution-sync CI workflow (`edpa-contribution-sync.yml`) and enrich `contributors[].signals[]`, but EDPA operates fully offline without them. No GitHub Project, no issue sync, no two-way coupling.

**Not source of truth:** hourly capacity, FTE records, derived hours for closed periods, signature status. These live in the Evidence & Reporting layer.

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
| `cw[P, item]` | Per-item share, computed by detect_contributors | 0.0–1.0 (Σ across persons = 1.0) |
| `contribution_score[P, item]` | Σ signal weights for P on item (audit input) | 0.5–10+ |

### 5.3 Evidence Detection (v1.11 + v1.17 yaml_edit)

CW computation lives in two collectors that feed the same additive
signal pool:

- `detect_contributors.py` (v1.11) — PR/issue API surfaces. Runs at
  PR merge via the `edpa-contributor-detect.yml` workflow.
- `yaml_edit_signals.py` (v1.17) — git diff over `.edpa/backlog/*.yaml`.
  Runs at engine close, scoped to the iteration window.

Both feed the same `contributors[].signals[]` aggregation. Signal
weights sum into `contribution_score`, which normalizes to per-item
`cw[P, item]` shares.

#### 5.3.1 PR / issue API signals (v1.11)

| Signal type | Default weight | Source | Auditor `ref` |
|-------------|---------------:|--------|---------------|
| `assignee` | 4.00 | Issue assignees | `issue#<num>` |
| `pr_author` | 3.40 | PR author | `pr#<num>` |
| `commit_author` | 2.78 | PR commit author (excl. PR author) | `pr#<num>/commit/<sha>` |
| `pr_reviewer` | 2.25 | PR reviews submitted | `pr#<num>/review/<id>` |
| `issue_comment` | 1.14 | Issue/PR comments (excl. bots) | `issue#<num>/comment/<id>` |
| `manual:pr_body` | explicit | `/contribute` in PR description | `pr#<num>/body` |
| `manual:commit_message` | explicit | `/contribute` in commit message | `commit/<sha>/message` |
| `manual:issue_body` | explicit | `/contribute` in issue description | `issue#<num>/body` |
| `manual:issue_comment` | explicit | `/contribute` in issue comment | `issue#<num>/comment/<id>` |
| `manual:pr_comment` | explicit | `/contribute` in PR-level comment | `pr#<num>/comment/<id>` |

#### 5.3.2 YAML-edit structural signals (v1.17)

Every commit touching `.edpa/backlog/<typ>/<id>.yaml` is itself
evidence of work on that item. Detection is **structural** (count
list bullets, top-level blocks, scalar changes) — it never tries to
semantically classify content (operator field-naming drift makes
that brittle). Auditor reviewing per-signal `ref` opens the commit
and sees the actual diff.

| Signal type | Default weight | Source | Auditor `ref` |
|-------------|---------------:|--------|---------------|
| `yaml_edit:create` | 5.00 | New file with +id+type+title | `commit/<sha>/<file>` |
| `yaml_edit:block_add` | 2.00 | Per top-level nested block added | `commit/<sha>/<file>` |
| `yaml_edit:list_grow` | 1.00 (cap 10) | Per net `- ` bullet added | `commit/<sha>/<file>` |
| `yaml_edit:scalar_change` | 0.50 | Per top-level scalar set | `commit/<sha>/<file>` |
| `yaml_edit:lines_volume` | min(3.0, n/30) | Substantive-edit proxy | `commit/<sha>/<file>` |
| `yaml_edit:contributors_rebalance` | 0.30 | Per new person added (NOT cw shifts) | `commit/<sha>/<file>` |
| `yaml_edit:revert` | -0.50 | Per net-removed block (negative) | `commit/<sha>/<file>` |

Built-in mitigations against gaming:

- **Bot authors** (`*[bot]@*`, `github-actions@*`) → 0 weight
- **Tool-generated commits** (`EDPA sync push:`, `EDPA: capacity override`,
  `EDPA setup state committed`) → 0 weight
- **Whitespace-only diffs** → 0 weight
- **Status-only changes** → 0 weight (transitions.py owns gate-event credit)
- **File renames / moves** → 0 weight (metadata only)
- **Bulk migrations** (`chore: rename`, `EDPA migrate`) → ×0.1 multiplier
- **Backdated commits** use `GIT_AUTHOR_DATE` for iteration-window check

Auto-detected signal weights live in `.edpa/config/cw_heuristics.yaml`
under `signals:` (PR/issue) and `yaml_edit_weights:` (v1.17). Both
are calibrated by `/edpa:calibrate`. Manual `/contribute @person weight:X`
directives carry the operator-supplied `weight:` value verbatim —
they are **additive signals**, not overrides.

Rules:
- All signals contribute additively to `contribution_score`; no priority dominance
- `cw[P, item] = contribution_score[P, item] / Σ_persons contribution_score[*, item]`
- Multiple `/contribute` lines for the same person stack additively
- Role labels are derived from signal types at display time only — never stored

See [`docs/evidence-detection.md`](evidence-detection.md) for the full
detection algorithm and [`docs/contribute-directive.md`](contribute-directive.md)
for `/contribute` usage patterns.

### 5.4 Calculation (single path, v1.14+ extended in v1.17)

The engine has **one calculation path**. It credits three kinds of
work events together and lets per-person ratio normalization split
the person's capacity across whichever items they touched:

1. **Story / Defect / Task Done credit** — items at `status: Done`
   get `JS × cw` per their contributors[]. cw shares come pre-computed
   from `detect_contributors.py` and (v1.17+) augmented in-memory by
   `yaml_edit_signals.py` before run_edpa. (v1.17 fix: pre-v1.17 the
   engine silently dropped Defects via a `level == "Story"` filter.)
2. **Parent gate transitions** — Feature/Epic/Initiative status
   transitions captured in git history (via `sync pull --commit`
   auto-commits) become synthetic events with effective JS =
   `parent.JS × gate_weights[type][transition]`. Parent contributors
   inherit cw shares from the parent's contributors[] block — and
   when the parent had no contributors[] populated (e.g., seeded
   without `--contributor`), v1.17 yaml_edit signals automatically
   credit the commit author who wrote the LBC / AC / NFRs.
3. **YAML-edit signals (v1.17)** — every commit on a backlog YAML
   inside the iteration window contributes structural signals
   (create / block_add / list_grow / scalar_change / lines_volume /
   contributors_rebalance / revert). These augment contributors[]
   in-memory before run_edpa; the frozen snapshot captures the
   augmented state for full audit trail.

When git history records no transitions and no yaml_edit activity,
only Done-item credit fires. The calculation is feature-preserving
across all setups.

> **`status: Done` requirement for Stories.** Stories still in
> `Backlog` / `Implementing` / `Validating` don't fire Done credit.
> If you want partial credit before iteration close, drive parent
> status transitions on the Feature/Epic that contains them — gate
> events fire on parent transitions even while their child Stories
> are mid-flight.

**v1.14 unified formula** (no role dominance, no Relevance Signal,
no mode selector):

```text
contribution_score[P, item] = Σ signal_weight × signal_fired(P, item)
cw[P, item]                 = contribution_score[P, item]
                              / Σ_persons contribution_score[*, item]
score[P, item]              = JobSize[item] × cw[P, item]
ratio[P, item]              = score[P, item] / Σ_items_of_P score
DerivedHours[P, item]       = ratio[P, item] × Capacity[P, I]
```

The pre-v1.14 `simple` / `full` / `gates` mode selector was removed.
`gates` was a strict superset of the others (degenerated to Done-only
when no transitions existed), so the single-path engine is
mathematically equivalent and operationally simpler.

### 5.5 Mathematical Guarantees

Two invariants hold by construction:

```text
1. Per-item:    Σ_persons cw[*, item] = 1.0
2. Per-person:  Σ_items   DerivedHours[P, *] = Capacity[P, I]
```

Invariant 1 follows from the sum-and-normalize aggregation: each
item's contributions sum to 1.0 by definition. Invariant 2 follows
from per-person ratio normalization across their items in the
iteration. Engine validates both at run time and refuses to write
the snapshot if either fails.

---

## 6. Two Views from One Dataset (v1.11)

### 6.1 What `cw` means in v1.11

Single semantic: **cw is the per-item share of contribution**.

```text
cw[P, item] = contribution_score[P, item] / Σ_persons contribution_score[*, item]
Σ_persons cw[*, item] = 1.0
```

`cw = 0.25` for person P on Story S-1 reads as **"P contributed 25%
of S-1's evidence-weighted work"**. Pre-v1.11 cw was an absolute
[0, 1] value with role-coupled semantics ("P was a reviewer, weight
0.25"), which was ambiguous between two normalizations. v1.11 fixes
the meaning to per-item share.

### 6.2 Per-Person View (Timesheets)

Answers: **How does person P's capacity distribute across their items
this iteration?**

```text
score[P, item] = JobSize[item] × cw[P, item]
ratio[P, item] = score[P, item] / Σ_items_of_P score
DerivedHours[P, item] = ratio[P, item] × Capacity[P, I]

Guarantee: Σ_items DerivedHours[P, *] = Capacity[P, I]
```

Output: **timesheet per person** — how many hours P spent on which
item.

### 6.3 Per-Item View (Cost Allocation)

Answers: **How does work on item X distribute across people?**

This view is **directly readable from `cw`** without further
computation — `cw[P, X]` IS X's share of P. To translate to hours:

```text
ItemHours[P, item] = JobSize[item] × cw[P, item] × hour_factor

Where hour_factor is set so that Σ_items_of_P JS × cw × hour_factor = Capacity[P]
```

Or equivalently, the per-item hours **sum to the same number** as
the per-person view's `DerivedHours[P, item]` — they're two ways to
read the same per-(person, item) hour value.

### 6.4 Example: Story S-200 (JobSize = 8)

Detected signals:
- turyna: assignee (4) + commit_author (1) + manual:pr_body weight=2 → score 7
- tuma: pr_author (2) + commit_author (1) + pr_reviewer (1) → score 4
- urbanek: issue_comment (0.5) → score 0.5

Σ score on S-200 = 11.5

| Contributor | Signals | contribution_score | cw (share) |
|---|---|---:|---:|
| Turyna | assignee + commit + manual | 7.0 | **0.609** |
| Tuma | pr_author + commit + pr_reviewer | 4.0 | **0.348** |
| Urbanek | issue_comment | 0.5 | **0.043** |
| **Σ** | | **11.5** | **1.000** |

**Per-person view** (each from their own capacity, assuming S-200 is
their only item this iteration):

| Contributor | JS × cw | Capacity | Hours on S-200 |
|---|---:|---:|---:|
| Turyna | 8 × 0.609 = 4.87 | 60h | 60.0h (sole item) |
| Tuma | 8 × 0.348 = 2.78 | 80h | 80.0h (sole item) |
| Urbanek | 8 × 0.043 = 0.35 | 40h | 40.0h (sole item) |

(In real iterations each person has multiple items; ratio
normalization across items spreads their capacity proportionally to
score per item.)

### 6.5 When to read cw vs hours

| Question | Read | From |
|----------|------|------|
| "What share of S-200's work was Turyna's?" | `cw[turyna, S-200]` | `contributors[].cw` directly |
| "How many hours did Turyna spend on S-200?" | `DerivedHours[turyna, S-200]` | engine output `items[].hours` |
| "How many hours did the whole team spend on S-200?" | Σ over `DerivedHours[*, S-200]` | engine output, summed across persons |
| "What's the team total this iteration?" | Σ over `DerivedHours[*, *]` | should equal Σ Capacity by invariant |

cw is normalized (sums to 1.0 per item, dimensionless). DerivedHours
is in hours (sums to capacity per person). Both come from the same
underlying data — no duplication.

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

### 8.5 Auto-Calibration of CW Heuristics

CW signal weights are tuned by a self-contained Monte Carlo + coordinate-descent optimizer. It does **not** require a hand-recorded ground-truth file and is runnable at any time — including before the first Planning Interval closes.

Principle: one file, one metric, two phases.

```text
Target:     .edpa/config/cw_heuristics.yaml (signals: section, 5 weights)
Metric:     mean_absolute_deviation (predicted CW vs synthetic true CW)
Direction:  lower
Optimizer:  .edpa/engine/scripts/calibrate_signals.py (LOCKED)
Corpus:     1000 synthetic team×iteration scenarios, generated in-process
Phases:     (1) MC random sampling → (2) coordinate-descent refinement
```

The optimizer generates its own ground truth procedurally — no `.edpa/data/ground_truth.yaml` is needed. Each candidate weight vector is scored as MAD over the synthetic corpus; the best vector is written back to `cw_heuristics.yaml.tmpl` when `--apply` is passed.

Invoke via the `/edpa:calibrate` skill:

```text
python3 .edpa/engine/scripts/calibrate_signals.py --scenarios 1000 --seed 42 --apply
```

Flags: `--scenarios N` (default 1000), `--seed`, `--quick` (smaller MC sample, smoke test), `--apply` (rewrite `cw_heuristics.yaml.tmpl`), `--report PATH` (JSON report).

Safety constraint: agent must NOT edit `calibrate_signals.py`. The synthetic corpus generator and the MAD cost function live inside the locked script intentionally — modifying the generator to favor a weight vector gamifies the metric.

Re-tuning with real data: the synthetic corpus is a prior. Once a closed PI yields team-confirmed CW corrections, a future real-data adapter can replace the synthetic corpus with those records and re-run the same optimizer. Until that adapter ships, the synthetic MC pipeline is the calibration path.

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
  .edpa/reports/iteration-{I}/edpa-results.xlsx    ← Team Summary + Item Costs tabs

PI Close → aggregation:
  .edpa/reports/planning-interval-{PI}/pi-summary-{PI}.md

Annual:
  .edpa/reports/2026/annual.xlsx
```

### 10.2 Freeze Rule
After Iteration Close: snapshot is created, frozen, evidence is never overwritten in-place, every correction is a new revision. Critical for audit defense.

### 10.3 Audit Principle
Auditability rests on: local git delivery evidence (commit_author, yaml_edit, gate_events, story_activity — reproducible from `git log`) + capacity registry + frozen snapshot + reproducible calculation + signed output (BankID).

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
