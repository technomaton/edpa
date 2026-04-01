import { create } from 'zustand';
import type { PIConfig, Person, Team, ProjectConfig, GitStatus } from '../types/edpa';
import { api } from '../lib/api';

interface ConfigStore {
  pi: PIConfig | null;
  project: ProjectConfig | null;
  people: Person[];
  teams: Team[];
  git: GitStatus | null;
  fetch: () => Promise<void>;
  fetchGit: () => Promise<void>;
}

export const useConfigStore = create<ConfigStore>((set) => ({
  pi: null,
  project: null,
  people: [],
  teams: [],
  git: null,

  fetch: async () => {
    const [configData, peopleData] = await Promise.all([
      api.getConfig(),
      api.getPeople(),
    ]);
    set({
      pi: configData.pi,
      project: configData.project || peopleData.project,
      people: peopleData.people,
      teams: peopleData.teams,
    });
  },

  fetchGit: async () => {
    const git = await api.getGitStatus();
    set({ git });
  },
}));
