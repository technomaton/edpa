import { create } from 'zustand';
import type { WorkItem } from '../types/edpa';
import { api } from '../lib/api';

interface BacklogStore {
  items: WorkItem[];
  loading: boolean;
  dirty: Set<string>;
  fetch: () => Promise<void>;
  updateItem: (id: string, changes: Partial<WorkItem>) => void;
  saveItem: (id: string) => Promise<void>;
  saveAll: () => Promise<void>;
}

const TYPE_DIRS: Record<string, string> = {
  Initiative: 'initiatives',
  Epic: 'epics',
  Feature: 'features',
  Story: 'stories',
  Defect: 'defects',
};

export const useBacklogStore = create<BacklogStore>((set, get) => ({
  items: [],
  loading: false,
  dirty: new Set(),

  fetch: async () => {
    set({ loading: true });
    const { items } = await api.getBacklog();
    set({ items, loading: false, dirty: new Set() });
  },

  updateItem: (id, changes) => {
    set(state => ({
      items: state.items.map(i => (i.id === id ? { ...i, ...changes } : i)),
      dirty: new Set(state.dirty).add(id),
    }));
  },

  saveItem: async (id) => {
    const item = get().items.find(i => i.id === id);
    if (!item) return;
    const typeDir = TYPE_DIRS[item.type];
    await api.updateItem(typeDir, id, item);
    set(state => {
      const dirty = new Set(state.dirty);
      dirty.delete(id);
      return { dirty };
    });
  },

  saveAll: async () => {
    const { dirty } = get();
    for (const id of dirty) {
      await get().saveItem(id);
    }
  },
}));
