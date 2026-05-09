import type { Person, WorkItem, Iteration, ProjectConfig, Team } from './edpa-engine';

export const project: ProjectConfig = {
  name: 'SaaS Platform',
  registration: 'DEMO-2026-001',
  organization: 'Acme Engineering',
  program: 'Internal',
};

// Cadence: Klasická (2/10) — 2-week iterations, 10-week PI, 4 delivery + 1 IP
export const config = {
  iterationWeeks: 2,
  piWeeks: 10,
  pi: 'PI-2026-1',
  year: 2026,
  piNum: 1,
};

export const teams: Team[] = [
  { id: 'Core', planning_factor: 0.8 },
  { id: 'Platform', planning_factor: 0.8 },
];

export const people: Person[] = [
  { id: 'alice', name: 'Alice', role: 'Arch', team: 'Core', fte: 0.75, capacity: 60 },
  { id: 'bob', name: 'Bob', role: 'Dev', team: 'Core', fte: 1.0, capacity: 80 },
  { id: 'carol', name: 'Carol', role: 'Dev', team: 'Core', fte: 0.75, capacity: 60 },
  { id: 'dave', name: 'Dave', role: 'DevOps', team: 'Platform', fte: 0.5, capacity: 40 },
  { id: 'eve', name: 'Eve', role: 'PM', team: 'Platform', fte: 0.5, capacity: 40 },
  { id: 'frank', name: 'Frank', role: 'Dev', team: 'Platform', fte: 0.5, capacity: 40 },
];

// PI-2026-1: 4 delivery iterations (2 weeks each) + 1 IP iteration
export const iterations: Iteration[] = [
  { id: 'PI-2026-1.1', name: 'PI-2026-1.1', dates: '1.4.–14.4.2026', status: 'closed' },
  { id: 'PI-2026-1.2', name: 'PI-2026-1.2', dates: '15.4.–28.4.2026', status: 'closed' },
  { id: 'PI-2026-1.3', name: 'PI-2026-1.3', dates: '29.4.–12.5.2026', status: 'closed' },
  { id: 'PI-2026-1.4', name: 'PI-2026-1.4', dates: '13.5.–26.5.2026', status: 'active' },
  { id: 'PI-2026-1.5', name: 'PI-2026-1.5 (IP)', dates: '27.5.–9.6.2026', status: 'planned' },
];

export const items: WorkItem[] = [
  // Epics
  { id: 'E-1', title: 'User Management', level: 'Epic', js: 13, bv: 13, tc: 8, rr_oe: 5, parentId: null, status: 'Implementing', iteration: null, contributors: [
    { personId: 'alice', cw: 0.30 }, { personId: 'eve', cw: 0.50 }, { personId: 'bob', cw: 0.15 }
  ]},
  { id: 'E-2', title: 'Billing & Subscriptions', level: 'Epic', js: 8, bv: 8, tc: 13, rr_oe: 8, parentId: null, status: 'Implementing', iteration: null, contributors: [
    { personId: 'alice', cw: 0.20 }, { personId: 'eve', cw: 0.55 }, { personId: 'frank', cw: 0.15 }
  ]},

  // Features under E-1
  { id: 'F-10', title: 'Auth Service', level: 'Feature', js: 8, bv: 8, tc: 5, rr_oe: 3, parentId: 'E-1', status: 'Done', iteration: null, contributors: [
    { personId: 'alice', cw: 0.35 }, { personId: 'bob', cw: 0.40 }, { personId: 'dave', cw: 0.25 }
  ]},
  { id: 'F-11', title: 'User Profile API', level: 'Feature', js: 5, bv: 5, tc: 5, rr_oe: 3, parentId: 'E-1', status: 'Implementing', iteration: null, contributors: [
    { personId: 'carol', cw: 0.45 }, { personId: 'frank', cw: 0.35 }, { personId: 'eve', cw: 0.20 }
  ]},

  // Features under E-2
  { id: 'F-20', title: 'Payment Gateway', level: 'Feature', js: 8, bv: 8, tc: 8, rr_oe: 5, parentId: 'E-2', status: 'Implementing', iteration: null, contributors: [
    { personId: 'bob', cw: 0.40 }, { personId: 'frank', cw: 0.35 }, { personId: 'dave', cw: 0.25 }
  ]},
  { id: 'F-21', title: 'Subscription Engine', level: 'Feature', js: 5, bv: 5, tc: 13, rr_oe: 8, parentId: 'E-2', status: 'Implementing', iteration: null, contributors: [
    { personId: 'carol', cw: 0.40 }, { personId: 'alice', cw: 0.30 }, { personId: 'eve', cw: 0.30 }
  ]},

  // Stories PI-2026-1.1 (all Done)
  { id: 'S-100', title: 'JWT auth implementation', level: 'Story', js: 8, bv: 8, tc: 5, rr_oe: 3, parentId: 'F-10', status: 'Done', iteration: 'PI-2026-1.1', contributors: [
    { personId: 'bob', cw: 1 }, { personId: 'alice', cw: 0.30 }
  ]},
  { id: 'S-101', title: 'OAuth2 integration', level: 'Story', js: 5, bv: 5, tc: 3, rr_oe: 2, parentId: 'F-10', status: 'Done', iteration: 'PI-2026-1.1', contributors: [
    { personId: 'bob', cw: 1 }, { personId: 'dave', cw: 0.6 }
  ]},
  { id: 'S-102', title: 'Auth unit tests', level: 'Story', js: 3, bv: 3, tc: 2, rr_oe: 1, parentId: 'F-10', status: 'Done', iteration: 'PI-2026-1.1', contributors: [
    { personId: 'alice', cw: 1 }
  ]},
  { id: 'S-103', title: 'Profile CRUD endpoints', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 2, parentId: 'F-11', status: 'Done', iteration: 'PI-2026-1.1', contributors: [
    { personId: 'carol', cw: 1 }, { personId: 'frank', cw: 0.6 }
  ]},
  { id: 'S-104', title: 'Profile validation', level: 'Story', js: 3, bv: 3, tc: 3, rr_oe: 1, parentId: 'F-11', status: 'Done', iteration: 'PI-2026-1.1', contributors: [
    { personId: 'frank', cw: 1 }, { personId: 'carol', cw: 0.25 }
  ]},

  // Stories PI-2026-1.2 (all Done)
  { id: 'S-105', title: 'Stripe integration', level: 'Story', js: 8, bv: 8, tc: 8, rr_oe: 5, parentId: 'F-20', status: 'Done', iteration: 'PI-2026-1.2', contributors: [
    { personId: 'bob', cw: 1 }, { personId: 'frank', cw: 0.6 }, { personId: 'dave', cw: 0.15 }
  ]},
  { id: 'S-106', title: 'Payment webhook handler', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 3, parentId: 'F-20', status: 'Done', iteration: 'PI-2026-1.2', contributors: [
    { personId: 'frank', cw: 1 }, { personId: 'bob', cw: 0.25 }
  ]},
  { id: 'S-107', title: 'Subscription plan model', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 3, parentId: 'F-21', status: 'Done', iteration: 'PI-2026-1.2', contributors: [
    { personId: 'carol', cw: 1 }, { personId: 'alice', cw: 0.6 }
  ]},
  { id: 'S-108', title: 'Plan upgrade flow', level: 'Story', js: 3, bv: 3, tc: 3, rr_oe: 2, parentId: 'F-21', status: 'Done', iteration: 'PI-2026-1.2', contributors: [
    { personId: 'carol', cw: 1 }, { personId: 'eve', cw: 0.20 }
  ]},
  { id: 'S-109', title: 'CI/CD pipeline setup', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 3, parentId: 'F-10', status: 'Done', iteration: 'PI-2026-1.2', contributors: [
    { personId: 'dave', cw: 1 }, { personId: 'alice', cw: 0.30 }
  ]},

  // Stories PI-2026-1.3 (all Done)
  { id: 'S-110', title: 'Invoice generation', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 3, parentId: 'F-20', status: 'Done', iteration: 'PI-2026-1.3', contributors: [
    { personId: 'frank', cw: 1 }, { personId: 'bob', cw: 0.25 }
  ]},
  { id: 'S-111', title: 'Billing dashboard UI', level: 'Story', js: 5, bv: 5, tc: 3, rr_oe: 2, parentId: 'F-20', status: 'Done', iteration: 'PI-2026-1.3', contributors: [
    { personId: 'carol', cw: 1 }, { personId: 'eve', cw: 0.6 }
  ]},
  { id: 'S-112', title: 'Usage metering', level: 'Story', js: 8, bv: 8, tc: 8, rr_oe: 5, parentId: 'F-21', status: 'Done', iteration: 'PI-2026-1.3', contributors: [
    { personId: 'bob', cw: 1 }, { personId: 'alice', cw: 0.6 }, { personId: 'dave', cw: 0.15 }
  ]},
  { id: 'S-113', title: 'Rate limiting', level: 'Story', js: 3, bv: 3, tc: 3, rr_oe: 5, parentId: 'F-11', status: 'Done', iteration: 'PI-2026-1.3', contributors: [
    { personId: 'dave', cw: 1 }, { personId: 'alice', cw: 0.30 }
  ]},
  { id: 'S-114', title: 'E2E test suite', level: 'Story', js: 3, bv: 3, tc: 2, rr_oe: 2, parentId: 'F-10', status: 'Done', iteration: 'PI-2026-1.3', contributors: [
    { personId: 'alice', cw: 1 }, { personId: 'bob', cw: 0.25 }
  ]},

  // Stories PI-2026-1.4 (active iteration — mix Done + In Progress)
  { id: 'S-115', title: 'API documentation', level: 'Story', js: 2, bv: 2, tc: 1, rr_oe: 1, parentId: 'F-10', status: 'Done', iteration: 'PI-2026-1.4', contributors: [
    { personId: 'alice', cw: 1 }, { personId: 'eve', cw: 0.20 }
  ]},
  { id: 'S-116', title: 'Architecture review', level: 'Story', js: 3, bv: 3, tc: 2, rr_oe: 3, parentId: 'F-11', status: 'Done', iteration: 'PI-2026-1.4', contributors: [
    { personId: 'alice', cw: 1 }, { personId: 'carol', cw: 0.25 }
  ]},
  { id: 'S-117', title: 'Performance tests', level: 'Story', js: 5, bv: 5, tc: 3, rr_oe: 3, parentId: 'F-20', status: 'Done', iteration: 'PI-2026-1.4', contributors: [
    { personId: 'bob', cw: 1 }, { personId: 'dave', cw: 0.25 }
  ]},
  { id: 'S-118', title: 'Data migration scripts', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 5, parentId: 'F-21', status: 'Implementing', iteration: 'PI-2026-1.4', contributors: [
    { personId: 'carol', cw: 1 }, { personId: 'frank', cw: 0.6 }
  ]},
  { id: 'S-119', title: 'Webhook retry logic', level: 'Story', js: 3, bv: 3, tc: 3, rr_oe: 2, parentId: 'F-20', status: 'Implementing', iteration: 'PI-2026-1.4', contributors: [
    { personId: 'frank', cw: 1 }, { personId: 'bob', cw: 0.25 }
  ]},
  { id: 'S-120', title: 'Security audit', level: 'Story', js: 5, bv: 5, tc: 5, rr_oe: 8, parentId: 'F-10', status: 'Implementing', iteration: 'PI-2026-1.4', contributors: [
    { personId: 'dave', cw: 1 }, { personId: 'alice', cw: 0.6 }, { personId: 'bob', cw: 0.15 }
  ]},

  // Stories PI-2026-1.5 (IP — all Planned)
  { id: 'S-121', title: 'Tech debt cleanup', level: 'Story', js: 5, bv: 3, tc: 2, rr_oe: 5, parentId: 'F-11', status: 'Backlog', iteration: 'PI-2026-1.5', contributors: [
    { personId: 'carol', cw: 1 }, { personId: 'alice', cw: 0.30 }
  ]},
  { id: 'S-122', title: 'Monitoring setup', level: 'Story', js: 3, bv: 3, tc: 3, rr_oe: 3, parentId: 'F-20', status: 'Backlog', iteration: 'PI-2026-1.5', contributors: [
    { personId: 'dave', cw: 1 }, { personId: 'frank', cw: 0.25 }
  ]},
];
