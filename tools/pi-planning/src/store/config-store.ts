import { create } from 'zustand';
import type { PIConfig, Person, Team, ProjectConfig, GitStatus } from '../types/edpa';
import { api } from '../lib/api';

interface ConfigStore {
  pis: PIConfig[];
  project: ProjectConfig | null;
  people: Person[];
  teams: Team[];
  git: GitStatus | null;
  // PI selection
  selectedPI: string | null;
  isReadonly: boolean;
  selectPI: (piId: string) => void;
  // Derived
  currentPI: () => PIConfig | undefined;
  // Data
  fetch: () => Promise<void>;
  fetchGit: () => Promise<void>;
}

export const useConfigStore = create<ConfigStore>((set, get) => ({
  pis: [],
  project: null,
  people: [],
  teams: [],
  git: null,
  selectedPI: null,
  isReadonly: false,

  selectPI: (piId: string) => {
    const pi = get().pis.find(p => p.id === piId);
    set({
      selectedPI: piId,
      isReadonly: pi?.status === 'closed',
    });
  },

  currentPI: () => {
    const { pis, selectedPI } = get();
    return pis.find(p => p.id === selectedPI);
  },

  fetch: async () => {
    const [configData, peopleData] = await Promise.all([
      api.getConfig(),
      api.getPeople(),
    ]);
    const pis = configData.pis || [];
    // Default: planning PI > active PI > first PI
    // (PI Planning tool is primarily for planning the next PI)
    const defaultPI = pis.find(p => p.status === 'planning')
      || pis.find(p => p.status === 'active')
      || pis[0];
    const selectedPI = defaultPI?.id || null;

    set({
      pis,
      project: configData.project || peopleData.project,
      people: peopleData.people,
      teams: peopleData.teams,
      selectedPI,
      isReadonly: defaultPI?.status === 'closed',
    });
  },

  fetchGit: async () => {
    const git = await api.getGitStatus();
    set({ git });
  },
}));
