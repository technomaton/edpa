// EDPA web engine — TypeScript mirror of the Python engine for the
// in-browser calculator on the marketing site. Gated calculation:
// Story Done + Feature/Epic gate transitions. cw is the per-item
// normalized share (Σ across persons = 1.0 per item).

export interface Person {
  id: string;
  name: string;
  role: string;
  team: string;
  fte: number;
  capacity: number;
  contract?: string;           // "HPP", "DPČ", etc. (display label only)
}

export interface Contribution {
  personId: string;
  cw: number;                  // per-item share (Σ across persons on this item = 1.0)
}

export interface WorkItem {
  id: string;
  title: string;
  level: 'Init' | 'Epic' | 'Feature' | 'Story';
  js: number;
  bv: number;
  tc: number;
  rr_oe: number;
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
  description?: string;
  domain?: string;
  funding?: {
    program?: string;
    registration?: string;
    period_start?: string;
    period_end?: string;
  };
}

/**
 * WSJF prioritization score: (BV + TC + RR&OE) / JS  (RR&OE = Risk Reduction & Opportunity Enablement, stored in `rr` field)
 */
export function wsjf(item: WorkItem): number {
  if (item.js > 0 && item.bv) {
    return Math.round(((item.bv + item.tc + item.rr_oe) / item.js) * 100) / 100;
  }
  return 0;
}

/**
 * EDPA per-person calculation — gated.
 *
 * Stories at status==='Done' get credited; Feature/Epic parents get
 * credited via gate transitions captured in git history (server-side
 * only; this in-browser engine doesn't read git, so for the calculator
 * we just credit non-Funnel parents declaratively).
 *
 *   score = JS × cw          (cw is per-item normalized share)
 *   ratio = score / Σ score  (per-person across their items)
 *   hours = ratio × capacity
 *
 * Invariant: Σ hours === capacity (within 0.01h)
 */
export function edpa(
  personId: string,
  iterationId: string,
  people: Person[],
  items: WorkItem[]
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
    const score = w.js * cw;
    return { ...w, cw, score, ratio: 0, hours: 0 };
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
 * EDPA per-item view: all contributors to a work item and their
 * derived hours for it.
 */
export function itemView(
  itemId: string,
  iterationId: string,
  people: Person[],
  items: WorkItem[]
): ItemViewResult | null {
  const item = items.find((w) => w.id === itemId);
  if (!item || !item.contributors) return null;

  const itId = iterationId || item.iteration;
  if (!itId) return null;

  const contributors = item.contributors.map((cn) => {
    const person = people.find((p) => p.id === cn.personId);
    if (!person) return {
      person: { id: '', name: '?', role: '', team: '', fte: 0, capacity: 0 },
      cw: cn.cw, hours: 0
    };
    const d = edpa(cn.personId, itId, people, items);
    const my = d ? d.items.find((x) => x.id === itemId) : null;
    return { person, cw: cn.cw, hours: my ? my.hours : 0 };
  });

  contributors.sort((a, b) => b.hours - a.hours);

  return {
    item,
    contributors,
    totalHours: contributors.reduce((a, x) => a + x.hours, 0),
  };
}
