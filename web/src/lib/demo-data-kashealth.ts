import type { Person, WorkItem, Iteration, ProjectConfig } from './edpa-engine';

export const project: ProjectConfig = {
  name: 'Medical Platform a Datovy e-shop',
  registration: 'CZ.01.01.01/01/24_062/0007440',
  organization: 'CVUT FBMI + Medicalc s.r.o.',
  program: 'OP TAK',
};

export const config = {
  iterationWeeks: 2,
  piWeeks: 10,
  pi: 'PI-2026-1',
  year: 2026,
  piNum: 1,
};

export const people: Person[] = [
  { id: 'urbanek', name: 'J. Urbanek', role: 'Arch', team: 'CVUT', fte: 0.5, capacity: 40 },
  { id: 'tuma', name: 'O. Tuma', role: 'DevSecOps', team: 'CVUT', fte: 1.0, capacity: 80 },
  { id: 'turyna', name: 'Turyna', role: 'Dev', team: 'CVUT', fte: 0.75, capacity: 60 },
  { id: 'matousek', name: 'Matousek', role: 'Dev', team: 'CVUT', fte: 0.75, capacity: 60 },
  { id: 'pm', name: 'PM Medicalc', role: 'PM', team: 'Medicalc', fte: 0.5, capacity: 40 },
  { id: 'd1', name: 'Sr Dev MC', role: 'Dev', team: 'Medicalc', fte: 0.5, capacity: 40 },
  { id: 'd2', name: 'DB Spec MC', role: 'Dev', team: 'Medicalc', fte: 0.5, capacity: 40 },
  { id: 'do', name: 'DevOps MC', role: 'Dev', team: 'Medicalc', fte: 0.25, capacity: 20 },
];

export const iterations: Iteration[] = [
  { id: 'PI-2026-1.1', name: 'PI-2026-1.1', dates: '1.4.--14.4.2026', status: 'closed' },
  { id: 'PI-2026-1.2', name: 'PI-2026-1.2', dates: '15.4.--28.4.2026', status: 'closed' },
  { id: 'PI-2026-1.3', name: 'PI-2026-1.3', dates: '29.4.--12.5.2026', status: 'closed' },
  { id: 'PI-2026-1.4', name: 'PI-2026-1.4', dates: '13.5.--26.5.2026', status: 'active' },
  { id: 'PI-2026-1.5', name: 'PI-2026-1.5 (IP)', dates: '27.5.--9.6.2026', status: 'planned' },
];

export const items: WorkItem[] = [
  // Initiative
  { id: 'I-1', title: 'Medical Platform & Datovy e-shop', level: 'Init', js: 0, bv: 0, tc: 0, rr: 0, parentId: null, status: 'Active', iteration: null, contributions: [] },

  // Epics
  { id: 'E-10', title: 'Anonymizacni modul', level: 'Epic', js: 13, bv: 13, tc: 8, rr: 8, parentId: 'I-1', status: 'Active', iteration: null, contributions: [
    { personId: 'urbanek', cw: 0.20, rs: 1 }, { personId: 'pm', cw: 0.60, rs: 1 }, { personId: 'turyna', cw: 0.10, rs: 0.6 }, { personId: 'd1', cw: 0.10, rs: 0.5 }
  ]},
  { id: 'E-11', title: 'Datovy e-shop API', level: 'Epic', js: 8, bv: 8, tc: 13, rr: 5, parentId: 'I-1', status: 'Active', iteration: null, contributions: [
    { personId: 'urbanek', cw: 0.15, rs: 0.8 }, { personId: 'pm', cw: 0.60, rs: 1 }, { personId: 'matousek', cw: 0.15, rs: 0.6 }, { personId: 'd2', cw: 0.10, rs: 0.5 }
  ]},
  { id: 'E-12', title: 'OMOP CDM integrace', level: 'Epic', js: 5, bv: 5, tc: 5, rr: 13, parentId: 'I-1', status: 'Active', iteration: null, contributions: [
    { personId: 'urbanek', cw: 0.15, rs: 0.6 }, { personId: 'pm', cw: 0.60, rs: 1 }, { personId: 'tuma', cw: 0.25, rs: 0.8 }
  ]},

  // Features
  { id: 'F-100', title: 'OMOP CDM Parser', level: 'Feature', js: 8, bv: 8, tc: 5, rr: 5, parentId: 'E-10', status: 'Done', iteration: null, contributions: [
    { personId: 'urbanek', cw: 0.30, rs: 1 }, { personId: 'tuma', cw: 0.30, rs: 1 }, { personId: 'turyna', cw: 0.40, rs: 0.8 }
  ]},
  { id: 'F-101', title: 'Data Upload API', level: 'Feature', js: 5, bv: 5, tc: 8, rr: 3, parentId: 'E-10', status: 'Done', iteration: null, contributions: [
    { personId: 'tuma', cw: 0.35, rs: 1 }, { personId: 'matousek', cw: 0.40, rs: 1 }, { personId: 'd1', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'F-102', title: 'Anonymizacni engine', level: 'Feature', js: 13, bv: 13, tc: 13, rr: 8, parentId: 'E-10', status: 'Active', iteration: null, contributions: [
    { personId: 'urbanek', cw: 0.35, rs: 1 }, { personId: 'turyna', cw: 0.35, rs: 1 }, { personId: 'd1', cw: 0.30, rs: 0.8 }
  ]},
  { id: 'F-110', title: 'Katalog datasetu', level: 'Feature', js: 8, bv: 8, tc: 8, rr: 3, parentId: 'E-11', status: 'Active', iteration: null, contributions: [
    { personId: 'matousek', cw: 0.45, rs: 1 }, { personId: 'd2', cw: 0.40, rs: 1 }, { personId: 'pm', cw: 0.15, rs: 0.5 }
  ]},
  { id: 'F-111', title: 'Objednavkovy system', level: 'Feature', js: 5, bv: 5, tc: 13, rr: 5, parentId: 'E-11', status: 'Active', iteration: null, contributions: [
    { personId: 'd1', cw: 0.40, rs: 1 }, { personId: 'd2', cw: 0.35, rs: 0.8 }, { personId: 'pm', cw: 0.25, rs: 0.8 }
  ]},
  { id: 'F-120', title: 'FHIR bridge', level: 'Feature', js: 8, bv: 5, tc: 5, rr: 13, parentId: 'E-12', status: 'Active', iteration: null, contributions: [
    { personId: 'tuma', cw: 0.40, rs: 1 }, { personId: 'do', cw: 0.45, rs: 1 }, { personId: 'urbanek', cw: 0.15, rs: 0.5 }
  ]},

  // Stories PI-2026-1.1 (all Done)
  { id: 'S-200', title: 'OMOP parser impl.', level: 'Story', js: 8, bv: 8, tc: 5, rr: 3, parentId: 'F-100', status: 'Done', iteration: 'PI-2026-1.1', contributions: [
    { personId: 'turyna', cw: 1, rs: 1 }, { personId: 'tuma', cw: 0.6, rs: 1 }, { personId: 'urbanek', cw: 0.25, rs: 0.8 }
  ]},
  { id: 'S-201', title: 'Unit testy OMOP', level: 'Story', js: 5, bv: 5, tc: 3, rr: 2, parentId: 'F-100', status: 'Done', iteration: 'PI-2026-1.1', contributions: [
    { personId: 'turyna', cw: 1, rs: 1 }, { personId: 'urbanek', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-202', title: 'OMOP validace schemat', level: 'Story', js: 3, bv: 3, tc: 2, rr: 2, parentId: 'F-100', status: 'Done', iteration: 'PI-2026-1.1', contributions: [
    { personId: 'tuma', cw: 1, rs: 1 }, { personId: 'turyna', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-203', title: 'Upload endpoint', level: 'Story', js: 5, bv: 5, tc: 5, rr: 2, parentId: 'F-101', status: 'Done', iteration: 'PI-2026-1.1', contributions: [
    { personId: 'tuma', cw: 1, rs: 1 }, { personId: 'matousek', cw: 0.6, rs: 1 }
  ]},
  { id: 'S-204', title: 'Upload UI komponenta', level: 'Story', js: 3, bv: 3, tc: 3, rr: 1, parentId: 'F-101', status: 'Done', iteration: 'PI-2026-1.1', contributions: [
    { personId: 'matousek', cw: 1, rs: 1 }, { personId: 'd1', cw: 0.25, rs: 0.6 }
  ]},

  // Stories PI-2026-1.2 (all Done)
  { id: 'S-205', title: 'Upload testy', level: 'Story', js: 2, bv: 2, tc: 2, rr: 1, parentId: 'F-101', status: 'Done', iteration: 'PI-2026-1.2', contributions: [
    { personId: 'd1', cw: 1, rs: 1 }
  ]},
  { id: 'S-206', title: 'Anon pipeline MVP', level: 'Story', js: 8, bv: 8, tc: 8, rr: 5, parentId: 'F-102', status: 'Done', iteration: 'PI-2026-1.2', contributions: [
    { personId: 'urbanek', cw: 1, rs: 1 }, { personId: 'turyna', cw: 0.6, rs: 1 }, { personId: 'd1', cw: 0.15, rs: 0.5 }
  ]},
  { id: 'S-207', title: 'K-anonymity algoritmus', level: 'Story', js: 5, bv: 5, tc: 5, rr: 3, parentId: 'F-102', status: 'Done', iteration: 'PI-2026-1.2', contributions: [
    { personId: 'turyna', cw: 1, rs: 1 }, { personId: 'urbanek', cw: 0.25, rs: 0.8 }
  ]},
  { id: 'S-208', title: 'Anonymizace testy', level: 'Story', js: 3, bv: 3, tc: 3, rr: 2, parentId: 'F-102', status: 'Done', iteration: 'PI-2026-1.2', contributions: [
    { personId: 'd1', cw: 1, rs: 1 }, { personId: 'turyna', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-209', title: 'Katalog UI', level: 'Story', js: 5, bv: 5, tc: 5, rr: 2, parentId: 'F-110', status: 'Done', iteration: 'PI-2026-1.2', contributions: [
    { personId: 'matousek', cw: 1, rs: 1 }, { personId: 'd2', cw: 0.6, rs: 0.8 }
  ]},
  { id: 'S-210', title: 'Katalog API', level: 'Story', js: 5, bv: 5, tc: 5, rr: 3, parentId: 'F-110', status: 'Done', iteration: 'PI-2026-1.2', contributions: [
    { personId: 'd2', cw: 1, rs: 1 }, { personId: 'matousek', cw: 0.25, rs: 0.6 }
  ]},

  // Stories PI-2026-1.3 (all Done)
  { id: 'S-211', title: 'Katalog search', level: 'Story', js: 3, bv: 3, tc: 2, rr: 1, parentId: 'F-110', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'matousek', cw: 1, rs: 1 }
  ]},
  { id: 'S-212', title: 'Objednavka workflow', level: 'Story', js: 5, bv: 5, tc: 8, rr: 3, parentId: 'F-111', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'd1', cw: 1, rs: 1 }, { personId: 'd2', cw: 0.6, rs: 0.8 }, { personId: 'pm', cw: 0.15, rs: 0.5 }
  ]},
  { id: 'S-213', title: 'Objednavka notifikace', level: 'Story', js: 3, bv: 3, tc: 3, rr: 2, parentId: 'F-111', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'd2', cw: 1, rs: 1 }, { personId: 'd1', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-214', title: 'FHIR parser', level: 'Story', js: 5, bv: 5, tc: 3, rr: 5, parentId: 'F-120', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'tuma', cw: 1, rs: 1 }, { personId: 'do', cw: 0.6, rs: 1 }
  ]},
  { id: 'S-215', title: 'FHIR mapping', level: 'Story', js: 8, bv: 5, tc: 5, rr: 8, parentId: 'F-120', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'do', cw: 1, rs: 1 }, { personId: 'tuma', cw: 0.6, rs: 1 }, { personId: 'urbanek', cw: 0.15, rs: 0.5 }
  ]},
  { id: 'S-216', title: 'CI/CD pipeline', level: 'Story', js: 5, bv: 5, tc: 5, rr: 3, parentId: 'F-101', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'tuma', cw: 1, rs: 1 }, { personId: 'do', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-217', title: 'Security scan setup', level: 'Story', js: 3, bv: 3, tc: 3, rr: 5, parentId: 'F-120', status: 'Done', iteration: 'PI-2026-1.3', contributions: [
    { personId: 'tuma', cw: 1, rs: 1 }
  ]},

  // Stories PI-2026-1.4 (mix: Done + In Progress)
  { id: 'S-218', title: 'API dokumentace', level: 'Story', js: 2, bv: 2, tc: 1, rr: 1, parentId: 'F-100', status: 'Done', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'urbanek', cw: 1, rs: 1 }, { personId: 'tuma', cw: 0.15, rs: 0.5 }
  ]},
  { id: 'S-219', title: 'Architektura review', level: 'Story', js: 3, bv: 3, tc: 2, rr: 3, parentId: 'F-102', status: 'Done', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'urbanek', cw: 1, rs: 1 }, { personId: 'turyna', cw: 0.25, rs: 0.6 }, { personId: 'pm', cw: 0.15, rs: 0.5 }
  ]},
  { id: 'S-220', title: 'Performance testy', level: 'Story', js: 5, bv: 5, tc: 3, rr: 3, parentId: 'F-111', status: 'Done', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'd1', cw: 1, rs: 1 }, { personId: 'tuma', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-221', title: 'Data validace modul', level: 'Story', js: 5, bv: 5, tc: 5, rr: 5, parentId: 'F-102', status: 'In Progress', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'turyna', cw: 1, rs: 1 }, { personId: 'd1', cw: 0.6, rs: 0.8 }
  ]},
  { id: 'S-222', title: 'DB migrace scripts', level: 'Story', js: 3, bv: 3, tc: 2, rr: 2, parentId: 'F-110', status: 'Done', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'd2', cw: 1, rs: 1 }, { personId: 'matousek', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-223', title: 'E2E integration testy', level: 'Story', js: 3, bv: 3, tc: 2, rr: 2, parentId: 'F-101', status: 'In Progress', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'matousek', cw: 1, rs: 1 }, { personId: 'd2', cw: 0.25, rs: 0.6 }
  ]},
  { id: 'S-224', title: 'Auth modul', level: 'Story', js: 5, bv: 5, tc: 5, rr: 5, parentId: 'F-111', status: 'In Progress', iteration: 'PI-2026-1.4', contributions: [
    { personId: 'd1', cw: 1, rs: 1 }, { personId: 'tuma', cw: 0.6, rs: 1 }, { personId: 'urbanek', cw: 0.15, rs: 0.5 }
  ]},

  // Stories PI-2026-1.5 (IP -- all Planned)
  { id: 'S-225', title: 'Anon edge cases', level: 'Story', js: 5, bv: 5, tc: 5, rr: 5, parentId: 'F-102', status: 'Planned', iteration: 'PI-2026-1.5', contributions: [
    { personId: 'turyna', cw: 1, rs: 1 }, { personId: 'urbanek', cw: 0.25, rs: 0.8 }
  ]},
  { id: 'S-226', title: 'Monitoring setup', level: 'Story', js: 3, bv: 3, tc: 3, rr: 3, parentId: 'F-120', status: 'Planned', iteration: 'PI-2026-1.5', contributions: [
    { personId: 'do', cw: 1, rs: 1 }, { personId: 'tuma', cw: 0.25, rs: 0.6 }
  ]},
];
