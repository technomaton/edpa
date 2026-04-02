import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { GitStatusBar } from './components/GitStatusBar';
import { ProgramBoard } from './views/ProgramBoard/ProgramBoard';
import { TeamBoard } from './views/TeamBoard/TeamBoard';
import { Prioritization } from './views/Prioritization/Prioritization';
import { ROAM } from './views/ROAM/ROAM';
import { People } from './views/People/People';
import { Calendar } from './views/Calendar/Calendar';
import { Objectives } from './views/Objectives/Objectives';
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
    // Poll git status every 10s
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
    <BrowserRouter>
      <div className="app">
        <Sidebar />
        <main className="main">
          <Routes>
            <Route path="/" element={<ProgramBoard />} />
            <Route path="/team" element={<TeamBoard />} />
            <Route path="/prioritize" element={<Prioritization />} />
            <Route path="/roam" element={<ROAM />} />
            <Route path="/people" element={<People />} />
            <Route path="/calendar" element={<Calendar />} />
            <Route path="/objectives" element={<Objectives />} />
          </Routes>
        </main>
        <GitStatusBar />
      </div>
    </BrowserRouter>
  );
}
