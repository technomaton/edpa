# Frequently Asked Questions

## General

### How is EDPA different from Toggl/Harvest/Clockify?

Those tools require **manual time entry**. EDPA derives hours automatically from your local git evidence — commits, yaml edits, status transitions, in-flight Story activity. No one fills timesheets. No one guesses how many hours they spent on what.

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
1. **Python CLI** (`plugin/edpa/scripts/engine.py`) — works anywhere with Python 3.10+
2. **Claude Code skills** — conversational interface for AI-assisted governance

The Python CLI is fully standalone. Claude Code skills provide a more convenient experience.

### Does EDPA work without GitHub?

V2.1 evidence is **local-first**: post-commit hook + engine reads from `git log` are pure git, no GitHub API. You can run EDPA on any git repo (GitLab, Gitea, Bitbucket, plain self-hosted). GitHub Projects sync is an *optional* PM/BO UI layer; the optional CI workflow can add `pr_reviewer` + `issue_comment` signals if you want them, but the system is fully functional without either.

### Does EDPA work with Jira instead of GitHub?

The core EDPA engine is git-native — it doesn't talk to either GitHub or Jira directly for evidence. If you want Jira as the PM UI instead of GitHub Projects, you'd swap the `sync` layer (optional anyway). The evidence collection (`commit_author`, `yaml_edit`, `gate_events`, `story_activity`) all runs against `git log` regardless of which UI tracks tickets.

## Evidence Detection

### What if someone works on something but doesn't commit?

EDPA v2.1 detects multiple evidence types beyond raw commits:
- **`yaml_edit:*`** — structural edits to `.edpa/backlog/*.md` (block adds, list growth, scalar changes, file create — captures refinement, AC, DoD work). D-26: materialized into the item's `evidence[]` with a structural `delta`; the engine reads the snapshot, not `git log`
- **`state_transition` / `gate_event`** — status changes (who/when/from→to) materialized into `evidence[]`; F/E/I gate scoring (LBC → design → refinement → Done) derives from them, and they double as delivery-lead-time analytics
- **`story_activity`** — C7.5 synthesizes in-flight Story credit when yaml_edit signals exist but the Story hasn't reached Done
- **`manual:commit_message`** — `/contribute @person weight:X` parsed from commit body by post-commit hook (explicit additive signal)
- **`pr_reviewer`, `issue_comment`** — optional, emitted only if you enable the CI workflow

PMs, architects, and other non-coding roles generate evidence through yaml edits (writing LBC, AC, DoD), the `/contribute` directive in commit bodies, and (if enabled) GitHub reviews/comments.

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
1. Local git delivery evidence (commit_author, yaml_edit, gate_events, story_activity — all reproducible from `git log`)
2. Capacity registry (versioned in Git)
3. Frozen snapshots (immutable)
4. Reproducible calculation (deterministic formula)
5. Digital signature support (BankID)

Whether your specific auditor accepts it depends on your grant program. The methodology document provides the formal specification.

### Can I modify a snapshot after it's frozen?

No. Snapshots are immutable. Corrections create new revisions:
```
.edpa/snapshots/PI-2026-1.3.json        # original
.edpa/snapshots/PI-2026-1.3_rev2.json   # correction (includes reason and diff)
```

## Setup

### Does EDPA work on Windows?

Yes, as of **2.1.9**. EDPA's Python scripts force UTF-8 on stdout/stderr and pin `encoding="utf-8"` on every file read/write, so progress glyphs (`✓ → ·`) and diacritics no longer raise `UnicodeEncodeError`/`UnicodeDecodeError` on a cp1250/cp1252 console. ID allocation also falls back to a pure-stdlib lock when the optional `filelock` package isn't installed. If you hit `ModuleNotFoundError: No module named 'filelock'` or a Unicode error during `/edpa:setup` on an older build, update to 2.1.9+.

### What cadence should I use?

Start with **Classic (2/10)**: 2-week iterations, 10-week Planning Intervals. Switch to **AI-Native (1/5)** after the first PI if your team's velocity supports it. See [cadence.md](cadence.md) for decision criteria.

### How many people can EDPA handle?

EDPA works for any team size. The reference implementation runs with 8 people / 4.75 FTE. The formula scales linearly — computation time depends on the number of (person, item) pairs, which is typically manageable even for 50+ person teams.
