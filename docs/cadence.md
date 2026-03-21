# Cadence Configuration

## Two variants

| Parameter | Classic (2/10) | AI-Native (1/5) |
|-----------|---------------|-----------------|
| Iteration | 2 weeks | 1 week |
| Planning Interval | 10 weeks (4+1 IP) | 5 weeks (4+1 IP) |
| Capacity 1.0 FTE / iter | 80h | 40h |
| Capacity 0.5 FTE / iter | 40h | 20h |
| Ceremony overhead | ~3% | ~6% |
| Story max JS | 8 | 5 |

## Naming convention

`PI-{year}-{pi_num}.{iter_num}`

Examples:
- `PI-2026-1` = 1st Planning Interval of 2026
- `PI-2026-1.3` = 3rd iteration in 1st PI of 2026
- `PI-2026-1.5 (IP)` = Innovation & Planning iteration

## When to switch from 2/10 to 1/5

Switch after first PI if:
- Average Story lead time < 3 days
- Backlog quality is stable (items well-prepared)
- Review flow is not a bottleneck
- WIP is low
- Governance reporting is automated (Actions running)
- Coordination overhead is not growing

## EDPA is cadence-agnostic

The formula works identically for both variants — only `Capacity[P, I]` changes.
