import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { EDPA_SNAPSHOT_SCHEMA, isSupportedSnapshot } from './types/snapshot';
import './index.css';

const root = document.getElementById('root')!;
const snap = typeof window !== 'undefined' ? window.__EDPA__ : undefined;

// Version handshake: a generated report carrying a schema this bundle does not
// support is refused with a visible message rather than silently mis-rendering.
if (snap && !isSupportedSnapshot(snap)) {
  root.innerHTML =
    '<div style="font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:1.5rem 1.75rem;' +
    'border:1px solid #d4604a;border-radius:10px;color:#5a1f15;background:#fdecea">' +
    '<h2 style="margin:0 0 .5rem">EDPA report is out of date</h2>' +
    `<p style="margin:.25rem 0">Generated for snapshot schema <b>v${snap.schema_version}</b>, ` +
    `but this viewer supports <b>v${EDPA_SNAPSHOT_SCHEMA}</b>.</p>` +
    '<p style="margin:.75rem 0 0">Regenerate it with the current EDPA:</p>' +
    `<pre style="margin:.4rem 0 0;padding:.6rem .8rem;background:#fff;border-radius:6px;overflow:auto">` +
    `python plugin/edpa/scripts/pi_planning.py --pi ${snap.pi ?? ''}</pre></div>`;
} else {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
