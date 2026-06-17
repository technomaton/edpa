import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import type { WorkItem, Person, Team, PIConfig, ProjectConfig, Iteration } from '../src/types/edpa.js';

const TYPE_DIRS: Record<string, string> = {
  Initiative: 'initiatives',
  Epic: 'epics',
  Feature: 'features',
  Story: 'stories',
  Defect: 'defects',
  Event: 'events',
  Risk: 'risks',
};

const PREFIX_TO_DIR: Record<string, string> = {
  I: 'initiatives',
  E: 'epics',
  F: 'features',
  S: 'stories',
  D: 'defects',
  EV: 'events',
  R: 'risks',
};

const TYPE_PREFIX: Record<string, string> = {
  Initiative: 'I',
  Epic: 'E',
  Feature: 'F',
  Story: 'S',
  Defect: 'D',
  Event: 'EV',
  Risk: 'R',
};

// ─── Markdown + YAML frontmatter helpers ────────────────────────────────
// Backlog items live as `.md` files: `---\n<yaml>\n---\n<markdown body>`.
// Structured metadata is in the frontmatter; prose (description, AC, notes)
// lives in the body. Mirrors plugin/edpa/scripts/_md_frontmatter.py.

const FRONTMATTER_DELIM = '---';

function splitFrontmatter(text: string): { yamlText: string; body: string } {
  if (!text) return { yamlText: '', body: '' };
  if (!text.startsWith(FRONTMATTER_DELIM)) return { yamlText: '', body: text };
  let rest = text.slice(FRONTMATTER_DELIM.length);
  if (rest.startsWith('\r\n')) rest = rest.slice(2);
  else if (rest.startsWith('\n')) rest = rest.slice(1);
  const endMatch = rest.match(/^---\s*$/m);
  if (!endMatch || endMatch.index === undefined) return { yamlText: '', body: text };
  const yamlText = rest.slice(0, endMatch.index);
  let body = rest.slice(endMatch.index + endMatch[0].length);
  if (body.startsWith('\r\n')) body = body.slice(2);
  else if (body.startsWith('\n')) body = body.slice(1);
  return { yamlText, body };
}

function parseMd(filePath: string): WorkItem | null {
  if (!fs.existsSync(filePath)) return null;
  const text = fs.readFileSync(filePath, 'utf-8');
  const { yamlText, body } = splitFrontmatter(text);
  const data = (yamlText.trim() ? (yaml.load(yamlText) as Record<string, unknown>) : {}) || {};
  return { ...data, body } as unknown as WorkItem;
}

function dumpMd(filePath: string, item: WorkItem): void {
  const { body, ...frontmatter } = item as WorkItem & { body?: string };
  const yamlText = Object.keys(frontmatter).length
    ? yaml.dump(frontmatter, { lineWidth: 120, noRefs: true, sortKeys: false })
    : '';
  const parts = [`${FRONTMATTER_DELIM}\n`, yamlText];
  if (!yamlText.endsWith('\n')) parts.push('\n');
  parts.push(`${FRONTMATTER_DELIM}\n`);
  const bodyText = body ?? '';
  if (bodyText) {
    if (!bodyText.startsWith('\n')) parts.push('\n');
    parts.push(bodyText);
    if (!bodyText.endsWith('\n')) parts.push('\n');
  }
  fs.writeFileSync(filePath, parts.join(''), 'utf-8');
}

export function findEdpaRoot(startDir: string): string | null {
  let dir = path.resolve(startDir);
  while (dir !== path.dirname(dir)) {
    if (fs.existsSync(path.join(dir, '.edpa', 'config', 'people.yaml'))) {
      return dir;
    }
    dir = path.dirname(dir);
  }
  return null;
}

export function loadAllItems(edpaRoot: string): WorkItem[] {
  const backlogDir = path.join(edpaRoot, '.edpa', 'backlog');
  const items: WorkItem[] = [];

  for (const typeDir of ['initiatives', 'epics', 'features', 'stories', 'defects', 'events', 'risks']) {
    const dir = path.join(backlogDir, typeDir);
    if (!fs.existsSync(dir)) continue;

    const files = fs.readdirSync(dir).filter(f => f.endsWith('.md')).sort();
    for (const file of files) {
      const item = parseMd(path.join(dir, file));
      if (item?.id) items.push(item);
    }
  }
  return items;
}

export function loadItem(edpaRoot: string, id: string): WorkItem | null {
  const prefix = id.split('-')[0];
  const typeDir = PREFIX_TO_DIR[prefix];
  if (!typeDir) return null;

  const filePath = path.join(edpaRoot, '.edpa', 'backlog', typeDir, `${id}.md`);
  return parseMd(filePath);
}

export function saveItem(edpaRoot: string, item: WorkItem): void {
  const typeDir = TYPE_DIRS[item.type];
  if (!typeDir) throw new Error(`Unknown type: ${item.type}`);

  const dir = path.join(edpaRoot, '.edpa', 'backlog', typeDir);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const filePath = path.join(dir, `${item.id}.md`);
  dumpMd(filePath, item);
}

export function loadPeopleConfig(edpaRoot: string): { people: Person[]; teams: Team[]; project: ProjectConfig } {
  const peoplePath = path.join(edpaRoot, '.edpa', 'config', 'people.yaml');
  const data = yaml.load(fs.readFileSync(peoplePath, 'utf-8')) as Record<string, unknown>;

  return {
    people: (data.people || []) as Person[],
    teams: (data.teams || []) as Team[],
    project: (data.project || { name: 'EDPA' }) as ProjectConfig,
  };
}

export function loadEdpaConfig(edpaRoot: string): { pis: PIConfig[] } {
  const configPath = path.join(edpaRoot, '.edpa', 'config', 'edpa.yaml');
  const data = (fs.existsSync(configPath)
    ? (yaml.load(fs.readFileSync(configPath, 'utf-8')) as Record<string, unknown>)
    : {}) || {};

  // Format 1 (current, v1.20+): per-PI + per-iteration files under .edpa/iterations/
  const piFromIterationsDir = loadPisFromIterationsDir(edpaRoot);
  if (piFromIterationsDir.length > 0) {
    return { pis: piFromIterationsDir };
  }

  // Format 2: explicit `pis:` array in edpa.yaml
  if (data.pis) {
    return { pis: data.pis as PIConfig[] };
  }

  // Format 3 (legacy): single `pi:` object in edpa.yaml
  const legacyPi = data.pi as Record<string, unknown> | undefined;
  if (legacyPi) {
    const piId = (legacyPi.current as string) || 'PI-unknown';
    const iterations = (legacyPi.iterations || []) as PIConfig['iterations'];
    const allClosed = iterations.every(it => it.status === 'closed');
    const hasActive = iterations.some(it => it.status === 'active');
    return {
      pis: [{
        id: piId,
        status: allClosed ? 'closed' : hasActive ? 'active' : 'planning',
        pi_iterations: iterations.length,
        iteration_weeks: (legacyPi.iteration_weeks as number) || 2,
        iterations,
      }],
    };
  }

  return { pis: [] };
}

function loadPisFromIterationsDir(edpaRoot: string): PIConfig[] {
  const iterDir = path.join(edpaRoot, '.edpa', 'iterations');
  if (!fs.existsSync(iterDir)) return [];

  const files = fs.readdirSync(iterDir).filter(f => f.endsWith('.yaml'));
  // PI files: pi: { id, ... } at root. Iteration files: iteration: { id, pi, ... }
  const piBlocks: Record<string, Record<string, unknown>> = {};
  const iterBlocks: Record<string, unknown>[] = [];

  for (const f of files) {
    const text = fs.readFileSync(path.join(iterDir, f), 'utf-8');
    const data = yaml.load(text) as Record<string, unknown> | null;
    if (!data) continue;
    if (data.pi && typeof data.pi === 'object') {
      const piData = data.pi as Record<string, unknown>;
      const id = piData.id as string | undefined;
      if (id) piBlocks[id] = piData;
    } else if (data.iteration && typeof data.iteration === 'object') {
      iterBlocks.push(data.iteration as Record<string, unknown>);
    }
  }

  // Group iterations by their pi field
  const iterByPi: Record<string, Iteration[]> = {};
  for (const it of iterBlocks) {
    const piId = it.pi as string | undefined;
    if (!piId) continue;
    iterByPi[piId] ||= [];
    iterByPi[piId].push({
      id: it.id as string,
      dates: formatIterationDates(it.start_date, it.end_date),
      start_date: isoDate(it.start_date),
      end_date: isoDate(it.end_date),
      status: (it.status as Iteration['status']) || 'planned',
      type: (it.type as string | undefined),
    });
  }
  // Sort iterations within each PI by id (lexicographic — `PI-2026-1.1` < `PI-2026-1.10`)
  for (const ids of Object.values(iterByPi)) {
    ids.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  }

  // Compose PIConfig per known PI
  const pis: PIConfig[] = [];
  for (const [piId, piData] of Object.entries(piBlocks)) {
    const iters = iterByPi[piId] || [];
    pis.push({
      id: piId,
      status: (piData.status as PIConfig['status']) || 'planning',
      pi_iterations: (piData.pi_iterations as number) || iters.length,
      iteration_weeks: (piData.iteration_weeks as number) || 2,
      iterations: iters,
      shared_services: piData.shared_services as string[] | undefined,
      events: piData.events as PIConfig['events'],
    });
  }

  // Also surface PIs that only have iteration files (no PI metadata file)
  for (const piId of Object.keys(iterByPi)) {
    if (piBlocks[piId]) continue;
    const iters = iterByPi[piId];
    const allClosed = iters.every(i => i.status === 'closed');
    const hasActive = iters.some(i => i.status === 'active');
    pis.push({
      id: piId,
      status: allClosed ? 'closed' : hasActive ? 'active' : 'planning',
      pi_iterations: iters.length,
      iteration_weeks: 2,
      iterations: iters,
    });
  }

  pis.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
  return pis;
}

function formatIterationDates(start: unknown, end: unknown): string {
  if (!start || !end) return '';
  // js-yaml parses `YYYY-MM-DD` as a Date; raw YAML strings stay strings.
  const fmt = (v: unknown) => {
    if (v instanceof Date) return `${v.getUTCDate()}.${v.getUTCMonth() + 1}.`;
    if (typeof v === 'string') {
      const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
      if (m) return `${parseInt(m[3])}.${parseInt(m[2])}.`;
      return v;
    }
    return String(v);
  };
  return `${fmt(start)}–${fmt(end)}`;
}

// ISO `YYYY-MM-DD` — keeps the authoritative year the pretty `dates` drops,
// so the calendar maps iterations onto the correct year (mirror _iso_date).
function isoDate(v: unknown): string | undefined {
  const p2 = (n: number) => (n < 10 ? '0' + n : '' + n);
  if (v instanceof Date) {
    return `${v.getUTCFullYear()}-${p2(v.getUTCMonth() + 1)}-${p2(v.getUTCDate())}`;
  }
  if (typeof v === 'string') {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  }
  return undefined;
}

export function nextId(edpaRoot: string, type: string): string {
  const typeDir = TYPE_DIRS[type];
  const prefix = TYPE_PREFIX[type];
  if (!typeDir || !prefix) throw new Error(`Unknown type: ${type}`);

  const dir = path.join(edpaRoot, '.edpa', 'backlog', typeDir);
  if (!fs.existsSync(dir)) return `${prefix}-1`;

  const files = fs.readdirSync(dir).filter(f => f.endsWith('.md'));
  let maxNum = 0;
  for (const f of files) {
    const match = f.match(/\d+/);
    if (match) maxNum = Math.max(maxNum, parseInt(match[0]));
  }
  return `${prefix}-${maxNum + 1}`;
}
