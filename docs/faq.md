# Frequently Asked Questions

## General

### How is EDPA different from Toggl/Harvest/Clockify?

Those tools require **manual time entry**. EDPA derives hours automatically from your GitHub delivery evidence. No one fills timesheets. No one guesses how many hours they spent on what.

| | EDPA | Toggl/Harvest |
|-|------|---------------|
| Manual input | Zero | Every person, every day |
| Data accuracy | Based on actual delivery evidence | Based on human memory |
| Audit trail | Immutable frozen snapshots | Editable logs |
| Mathematical guarantee | Sum always = capacity | No guarantee |

### How is EDPA different from LinearB/Pluralsight Flow?

Those tools measure **developer productivity metrics** (cycle time, PR throughput, etc.). EDPA produces **actual hour allocations** for financial reporting and audit compliance. Different purpose entirely.

### Does EDPA work without Claude Code?

Yes. EDPA has two interfaces:
1. **Python CLI** (`scripts/edpa_engine.py`) — works anywhere with Python 3.10+
2. **Claude Code skills** — conversational interface for AI-assisted governance

The Python CLI is fully standalone. Claude Code skills provide a more convenient experience.

### Does EDPA work with Jira instead of GitHub?

Not currently. EDPA is GitHub-native — it reads evidence from GitHub Issues, PRs, commits, and reviews. Jira support would require a different evidence detection layer. Contributions welcome!

## Evidence Detection

### What if someone works on something but doesn't commit?

EDPA detects multiple evidence types beyond commits:
- **Issue assignee** (strongest signal)
- **PR author** or **reviewer**
- **Issue/PR comments** (design discussions count)
- **Manual `/contribute` command** (explicit override)

PMs, architects, and other non-coding roles generate evidence through reviews, comments, and the `/contribute` command.

### What if the heuristic assigns wrong weights?

Two options:
1. **Manual override:** Add `/contribute @person weight:0.6` to the issue
2. **Auto-calibration:** After first Planning Interval, run the Karpathy autoresearch loop to optimize heuristics based on team-confirmed ground truth

### What about pair programming?

Both people should have evidence: one as PR author, the other as committer or via `/contribute`. The `/contribute` command is specifically designed for cases where Git evidence doesn't capture all contributors.

## Math & Guarantees

### How can derived hours always equal capacity?

Because EDPA uses **proportional allocation**, not fixed hour estimation:

```
DerivedHours[P, item] = (Score[P, item] / TotalScores[P]) x Capacity[P]
```

The ratios always sum to 1.0, so hours always sum to capacity. This is a mathematical property of the formula, not an approximation.

### What if someone has zero items in an iteration?

They get 0 derived hours. This is flagged as a process issue — either:
- They were on vacation (adjust capacity to 0)
- Their work wasn't tracked properly (add evidence retroactively)
- They were misassigned (update the capacity registry)

### What about items with no Job Size?

They're excluded with a warning. Job Size is required for EDPA calculation. Set it during planning (Definition of Ready).

## Audit & Compliance

### Is EDPA accepted by EU grant auditors?

EDPA is designed for EU compliance (OP TAK, Horizon Europe). Its audit trail includes:
1. GitHub delivery evidence (living data)
2. Capacity registry (versioned in Git)
3. Frozen snapshots (immutable)
4. Reproducible calculation (deterministic formula)
5. Digital signature support (BankID)

Whether your specific auditor accepts it depends on your grant program. The methodology document provides the formal specification.

### Can I modify a snapshot after it's frozen?

No. Snapshots are immutable. Corrections create new revisions:
```
snapshots/PI-2026-1.3.json        # original
snapshots/PI-2026-1.3_rev2.json   # correction (includes reason and diff)
```

## Setup

### What cadence should I use?

Start with **Classic (2/10)**: 2-week iterations, 10-week Planning Intervals. Switch to **AI-Native (1/5)** after the first PI if your team's velocity supports it. See [cadence.md](cadence.md) for decision criteria.

### How many people can EDPA handle?

EDPA works for any team size. The reference implementation runs with 8 people / 4.75 FTE. The formula scales linearly — computation time depends on the number of (person, item) pairs, which is typically manageable even for 50+ person teams.
