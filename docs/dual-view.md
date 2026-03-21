# Dual-View CW: Two Questions, One Dataset

## The problem

CW = 0.25 for a reviewer can mean two things:
- "This item took 25% of their attention vs their other items" → capacity distribution
- "They did 25% of the work on this item" → cost allocation

These are different questions. EDPA answers both from the same data.

## Per-person normalization (timesheets)

**Question:** How does person P's capacity distribute across their items?

```
DerivedHours[P, item] = (Score[P, item] / Σ Score[P, *]) × Capacity[P, I]
Guarantee: Σ DerivedHours[P, *] = Capacity[P, I]
```

Output: **timesheet per person** — how many hours P spent on each item.

## Per-item normalization (cost allocation)

**Question:** How does work on item X distribute across people?

```
ItemShare[P, item] = DerivedHours[P, item] / Σ DerivedHours[*, item]
Guarantee: Σ ItemShare[*, item] = 100%
```

Output: **cost card per deliverable** — who invested how much into this item.

## Example: Story S-200 (JS: 8)

**Per-person** (each from THEIR capacity):

| Person | CW | Score | Their Capacity | Their ΣScores | Hours on S-200 |
|--------|-----|-------|---------------|--------------|----------------|
| Turyna (Dev, owner) | 1.0 | 8.0 | 60h | 42.3 | 11.3h |
| Tůma (DevSecOps) | 0.6 | 4.8 | 80h | 58.1 | 6.6h |
| Urbánek (Arch, review) | 0.25 | 2.0 | 40h | 28.6 | 2.8h |

**Per-item** (how S-200's 20.7h distributes):

| Person | Hours | Share |
|--------|-------|-------|
| Turyna | 11.3h | 54.6% |
| Tůma | 6.6h | 31.9% |
| Urbánek | 2.8h | 13.5% |
| **Total** | **20.7h** | **100%** |

## When to use which

| View | Question | Output | Guarantee |
|------|----------|--------|-----------|
| Per-person | How much time did P spend on what? | Timesheet | Σ = capacity |
| Per-item | How much did item X cost? | Cost allocation | Σ shares = 100% |
