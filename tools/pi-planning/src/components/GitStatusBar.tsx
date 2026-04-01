import { useState } from 'react';
import { useConfigStore } from '../store/config-store';
import { useBacklogStore } from '../store/backlog-store';
import { api } from '../lib/api';

export function GitStatusBar() {
  const git = useConfigStore(s => s.git);
  const fetchGit = useConfigStore(s => s.fetchGit);
  const dirty = useBacklogStore(s => s.dirty);
  const saveAll = useBacklogStore(s => s.saveAll);
  const [committing, setCommitting] = useState(false);
  const [message, setMessage] = useState('');

  const handleCommit = async () => {
    if (!message.trim()) return;
    setCommitting(true);
    try {
      await saveAll();
      await api.commit(message);
      setMessage('');
      await fetchGit();
    } finally {
      setCommitting(false);
    }
  };

  return (
    <footer className="git-bar">
      <div className="git-bar__branch">
        <span className="git-bar__icon">⎇</span>
        {git?.branch || '...'}
      </div>
      {dirty.size > 0 && (
        <span className="git-bar__dirty">{dirty.size} unsaved</span>
      )}
      {(git?.dirty.length ?? 0) > 0 && (
        <span className="git-bar__files">{git!.dirty.length} changed files</span>
      )}
      <div className="git-bar__commit">
        <input
          className="git-bar__input"
          placeholder="Commit message..."
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCommit()}
        />
        <button
          className="git-bar__btn"
          onClick={handleCommit}
          disabled={committing || !message.trim()}
        >
          {committing ? '...' : 'Commit'}
        </button>
      </div>
    </footer>
  );
}
