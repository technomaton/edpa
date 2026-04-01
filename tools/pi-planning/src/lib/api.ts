const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  getBacklog: () => request<{ items: import('../types/edpa').WorkItem[] }>('/backlog'),
  updateItem: (type: string, id: string, data: Partial<import('../types/edpa').WorkItem>) =>
    request<import('../types/edpa').WorkItem>(`/backlog/${type}/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getPeople: () =>
    request<{
      people: import('../types/edpa').Person[];
      teams: import('../types/edpa').Team[];
      project: import('../types/edpa').ProjectConfig;
    }>('/people'),

  getConfig: () =>
    request<{
      pis: import('../types/edpa').PIConfig[];
      project: import('../types/edpa').ProjectConfig;
    }>('/config'),

  getGitStatus: () => request<import('../types/edpa').GitStatus>('/git/status'),
  commit: (message: string) =>
    request<{ hash: string }>('/git/commit', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  createBranch: (name: string) =>
    request<{ branch: string }>('/git/branch', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
};
