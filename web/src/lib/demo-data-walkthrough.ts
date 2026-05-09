import type { Person, WorkItem, Iteration, Team } from './edpa-engine';

// Default: 40h/week, 1-week iteration → capacity = FTE × 40
export const people: Person[] = [
  { id: 'alice', name: 'Alice', role: 'Architect', team: 'core', fte: 0.75, capacity: 30 },
  { id: 'bob',   name: 'Bob',   role: 'Developer', team: 'core', fte: 1.0,  capacity: 40 },
  { id: 'carol', name: 'Carol', role: 'PM',        team: 'core', fte: 0.5,  capacity: 20 },
];

// cw is per-item normalized share — Σ across persons on each item = 1.0
export const items: WorkItem[] = [
  {
    id: 'S-1', title: 'Auth service', level: 'Story', js: 8,
    bv: 8, tc: 5, rr: 3, parentId: null, status: 'Done', iteration: 'demo-1',
    contributors: [
      { personId: 'alice', cw: 0.23 },
      { personId: 'bob',   cw: 0.77 },
    ],
  },
  {
    id: 'S-2', title: 'API endpoints', level: 'Story', js: 5,
    bv: 5, tc: 3, rr: 2, parentId: null, status: 'Done', iteration: 'demo-1',
    contributors: [
      { personId: 'bob',   cw: 0.80 },
      { personId: 'carol', cw: 0.20 },
    ],
  },
  {
    id: 'S-3', title: 'Architecture review', level: 'Story', js: 3,
    bv: 3, tc: 2, rr: 5, parentId: null, status: 'Done', iteration: 'demo-1',
    contributors: [
      { personId: 'alice', cw: 0.69 },
      { personId: 'bob',   cw: 0.17 },
      { personId: 'carol', cw: 0.14 },
    ],
  },
  {
    id: 'S-4', title: 'Project planning', level: 'Story', js: 2,
    bv: 2, tc: 3, rr: 1, parentId: null, status: 'Done', iteration: 'demo-1',
    contributors: [
      { personId: 'alice', cw: 0.13 },
      { personId: 'carol', cw: 0.87 },
    ],
  },
];

export const iterations: Iteration[] = [
  { id: 'demo-1', name: 'Iterace 1', dates: '2026-03-17 — 2026-03-21', status: 'closed' },
];

export const teams: Team[] = [
  { id: 'core', planning_factor: 0.8 },
];
