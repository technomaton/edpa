import { create } from 'zustand';
import type { PIConfig, Person, Team, ProjectConfig, GitStatus, Iteration } from '../types/edpa';
import { api } from '../lib/api';

interface PIInfo {
  id: string;           // PI-2026-1
  iterations: Iteration[];
  status: 'planning' | 'active' | 'closed';
}

interface ConfigStore {
  pi: PIConfig | null;
  project: ProjectConfig | null;
  people: Person[];
  teams: Team[];
  git: GitStatus | null;
  // PI selection
  selectedPI: string | null;   // PI-2026-1
  availablePIs: PIInfo[];
  isReadonly: boolean;
  selectPI: (piId: string) => void;
  // Data
  fetch: () => Promise<void>;
  fetchGit: () => Promise<void>;
}

function derivePIStatus(iterations: Iteration[]): 'planning' | 'active' | 'closed' {
  if (iterations.every(it => it.status === 'closed')) return 'closed';
  if (iterations.some(it => it.status === 'active')) return 'active';
  return 'planning';
}

function groupByPI(iterations: Iteration[]): PIInfo[] {
  const map: Record<string, Iteration[]> = {};
  for (const it of iterations) {
    // PI-2026-1.3 → PI-2026-1
    const piId = it.id.replace(/\.\d+$/, '');
    if (!map[piId]) map[piId] = [];
    map[piId].push(it);
  }
  return Object.entries(map).map(([id, iters]) => ({
    id,
    iterations: iters,
    status: derivePIStatus(iters),
  }));
}

export const useConfigStore = create<ConfigStore>((set, get) => ({
  pi: null,
  project: null,
  people: [],
  teams: [],
  git: null,
  selectedPI: null,
  availablePIs: [],
  isReadonly: false,

  selectPI: (piId: string) => {
    const pis = get().availablePIs;
    const selected = pis.find(p => p.id === piId);
    set({
      selectedPI: piId,
      isReadonly: selected?.status === 'closed',
    });
  },

  fetch: async () => {
    const [configData, peopleData] = await Promise.all([
      api.getConfig(),
      api.getPeople(),
    ]);
    const pi = configData.pi;
    const availablePIs = groupByPI(pi?.iterations || []);
    const currentPI = pi?.current || availablePIs[0]?.id || null;
    const currentInfo = availablePIs.find(p => p.id === currentPI);

    set({
      pi,
      project: configData.project || peopleData.project,
      people: peopleData.people,
      teams: peopleData.teams,
      availablePIs,
      selectedPI: currentPI,
      isReadonly: currentInfo?.status === 'closed',
    });
  },

  fetchGit: async () => {
    const git = await api.getGitStatus();
    set({ git });
  },
}));
