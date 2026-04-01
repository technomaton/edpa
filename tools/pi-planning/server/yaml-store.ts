import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import type { WorkItem, Person, Team, PIConfig, ProjectConfig } from '../src/types/edpa.js';

const TYPE_DIRS: Record<string, string> = {
  Initiative: 'initiatives',
  Epic: 'epics',
  Feature: 'features',
  Story: 'stories',
  Defect: 'defects',
};

const PREFIX_TO_DIR: Record<string, string> = {
  I: 'initiatives',
  E: 'epics',
  F: 'features',
  S: 'stories',
  D: 'defects',
};

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

  for (const typeDir of ['initiatives', 'epics', 'features', 'stories', 'defects']) {
    const dir = path.join(backlogDir, typeDir);
    if (!fs.existsSync(dir)) continue;

    const files = fs.readdirSync(dir).filter(f => f.endsWith('.yaml')).sort();
    for (const file of files) {
      const content = fs.readFileSync(path.join(dir, file), 'utf-8');
      const item = yaml.load(content) as WorkItem;
      if (item?.id) items.push(item);
    }
  }
  return items;
}

export function loadItem(edpaRoot: string, id: string): WorkItem | null {
  const prefix = id.split('-')[0];
  const typeDir = PREFIX_TO_DIR[prefix];
  if (!typeDir) return null;

  const filePath = path.join(edpaRoot, '.edpa', 'backlog', typeDir, `${id}.yaml`);
  if (!fs.existsSync(filePath)) return null;

  return yaml.load(fs.readFileSync(filePath, 'utf-8')) as WorkItem;
}

export function saveItem(edpaRoot: string, item: WorkItem): void {
  const typeDir = TYPE_DIRS[item.type];
  if (!typeDir) throw new Error(`Unknown type: ${item.type}`);

  const dir = path.join(edpaRoot, '.edpa', 'backlog', typeDir);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const filePath = path.join(dir, `${item.id}.yaml`);
  const content = yaml.dump(item, { lineWidth: 120, noRefs: true, sortKeys: false });
  fs.writeFileSync(filePath, content, 'utf-8');
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

export function loadEdpaConfig(edpaRoot: string): { pi: PIConfig } {
  const configPath = path.join(edpaRoot, '.edpa', 'config', 'edpa.yaml');
  const data = yaml.load(fs.readFileSync(configPath, 'utf-8')) as Record<string, unknown>;

  return {
    pi: data.pi as PIConfig,
  };
}

export function nextId(edpaRoot: string, type: string): string {
  const typeDir = TYPE_DIRS[type];
  if (!typeDir) throw new Error(`Unknown type: ${type}`);

  const dir = path.join(edpaRoot, '.edpa', 'backlog', typeDir);
  if (!fs.existsSync(dir)) return `${type[0]}-1`;

  const prefix = type[0];
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.yaml'));
  let maxNum = 0;
  for (const f of files) {
    const match = f.match(/\d+/);
    if (match) maxNum = Math.max(maxNum, parseInt(match[0]));
  }
  return `${prefix}-${maxNum + 1}`;
}
