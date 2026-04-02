export interface Person {
  id: string;
  name: string;
  role: string;
  team: string;
  fte: number;
  capacity: number;
  contract?: string;           // "HPP", "DPČ", etc.
  evidence_scope?: string[];   // item ID patterns for this contract
  evidence_default?: boolean;  // true = fallback for unscoped evidence
}

export interface Contribution {
  personId: string;
  cw: number;
  rs: number;
}

export interface WorkItem {
  id: string;
  title: string;
  level: 'Init' | 'Epic' | 'Feature' | 'Story';
  js: number;
  bv: number;
  tc: number;
  rr: number;
  parentId: string | null;
  status: string;
  iteration: string | null;
  contributors: Contribution[];
}

export interface Iteration {
  id: string;
  name: string;
  dates: string;
  status: 'closed' | 'active' | 'planned';
}

export interface ScoredItem extends WorkItem {
  cw: number;
  rs: number;
  score: number;
  ratio: number;
  hours: number;
}

export interface EdpaResult {
  person: Person;
  iteration: string;
  items: ScoredItem[];
  totalScore: number;
  totalHours: number;
  ok: boolean;
}

export interface ItemViewResult {
  item: WorkItem;
  contributors: {
    person: Person;
    cw: number;
    rs: number;
    hours: number;
  }[];
  totalHours: number;
}

export interface Team {
  id: string;
  planning_factor: number;
}

export interface ProjectConfig {
  name: string;
  registration: string;
  organization: string;
  program: string;
}

/**
 * WSJF prioritization score: (BV + TC + RR) / JS
 */
export function wsjf(item: WorkItem): number {
  if (item.js > 0 && item.bv) {
    return Math.round(((item.bv + item.tc + item.rr) / item.js) * 100) / 100;
  }
  return 0;
}

/**
 * EDPA Per-Person calculation.
 *
 * Computes derived hours for a person in an iteration.
 *
 * Relevant items:
 *  - Stories: must be in the iteration AND status === 'Done'
 *  - Features / Epics: must not be 'Planned'
 *  - The person must appear in the item's contributors
 *
 * Score formula:
 *  - Simple mode: Score = JS * CW
 *  - Full mode:   Score = JS * CW * RS
 *
 * DerivedHours = (Score / SumScores) * Capacity
 * Guarantee: Sum(DerivedHours) === Capacity (within 0.01h)
 */
export function edpa(
  personId: string,
  iterationId: string,
  people: Person[],
  items: WorkItem[],
  mode: 'simple' | 'full'
): EdpaResult | null {
  const person = people.find((p) => p.id === personId);
  if (!person) return null;

  const relevant = items.filter((w) => {
    if (!w.contributors || !w.contributors.some((c) => c.personId === personId))
      return false;
    if (w.level === 'Story') return w.iteration === iterationId && w.status === 'Done';
    if (w.level === 'Feature' || w.level === 'Epic') return w.status !== 'Funnel';
    return false;
  });

  const scored: ScoredItem[] = relevant.map((w) => {
    const cn = w.contributors.find((c) => c.personId === personId);
    const cw = cn ? cn.cw : 0;
    const rs = cn ? cn.rs : 1;
    const score = mode === 'full' ? w.js * cw * rs : w.js * cw;
    return { ...w, cw, rs, score, ratio: 0, hours: 0 };
  });

  const sum = scored.reduce((a, x) => a + x.score, 0);
  const derived = scored.map((x) => ({
    ...x,
    ratio: sum > 0 ? x.score / sum : 0,
    hours: sum > 0 ? (x.score / sum) * person.capacity : 0,
  }));

  derived.sort((a, b) => b.score - a.score);

  const totalHours = derived.reduce((a, x) => a + x.hours, 0);

  return {
    person,
    iteration: iterationId,
    items: derived,
    totalScore: sum,
    totalHours,
    ok: sum > 0 ? Math.abs(totalHours - person.capacity) < 0.01 : true,
  };
}

/**
 * EDPA Per-Item view.
 *
 * Shows all contributors to a work item and their derived hours for it.
 */
export function itemView(
  itemId: string,
  iterationId: string,
  people: Person[],
  items: WorkItem[],
  mode: 'simple' | 'full'
): ItemViewResult | null {
  const item = items.find((w) => w.id === itemId);
  if (!item || !item.contributors) return null;

  const itId = iterationId || item.iteration;
  if (!itId) return null;

  const contributors = item.contributors.map((cn) => {
    const person = people.find((p) => p.id === cn.personId);
    if (!person) return { person: { id: '', name: '?', role: '', team: '', fte: 0, capacity: 0 }, cw: cn.cw, rs: cn.rs, hours: 0 };
    const d = edpa(cn.personId, itId, people, items, mode);
    const my = d ? d.items.find((x) => x.id === itemId) : null;
    return { person, cw: cn.cw, rs: cn.rs, hours: my ? my.hours : 0 };
  });

  contributors.sort((a, b) => b.hours - a.hours);

  return {
    item,
    contributors,
    totalHours: contributors.reduce((a, x) => a + x.hours, 0),
  };
}
