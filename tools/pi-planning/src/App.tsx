import { useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { GitStatusBar } from './components/GitStatusBar';
import { Canvas } from './views/Canvas/Canvas';
import { useBacklogStore } from './store/backlog-store';
import { useConfigStore } from './store/config-store';

export function App() {
  const fetchBacklog = useBacklogStore(s => s.fetch);
  const loading = useBacklogStore(s => s.loading);
  const fetchConfig = useConfigStore(s => s.fetch);
  const fetchGit = useConfigStore(s => s.fetchGit);

  useEffect(() => {
    fetchConfig();
    fetchBacklog();
    fetchGit();
    const interval = setInterval(fetchGit, 10_000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="loading">
        <span>Loading EDPA backlog...</span>
      </div>
    );
  }

  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <Canvas />
      </main>
      <GitStatusBar />
    </div>
  );
}
