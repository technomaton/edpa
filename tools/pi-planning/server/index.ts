import express from 'express';
import cors from 'cors';
import path from 'path';
import { findEdpaRoot } from './yaml-store.js';
import { backlogRoutes } from './routes/backlog.js';
import { peopleRoutes } from './routes/people.js';
import { configRoutes } from './routes/config.js';
import { gitRoutes } from './routes/git.js';

const PORT = parseInt(process.env.PORT || '3001');
const isProd = process.argv.includes('--prod');

// Find EDPA root — walk up from cwd or use --root flag
const rootFlag = process.argv.find((_, i, a) => a[i - 1] === '--root');
const edpaRoot = rootFlag ? path.resolve(rootFlag) : findEdpaRoot(process.cwd());

if (!edpaRoot) {
  console.error('Cannot find .edpa/ directory. Run from a project with EDPA or use --root <path>');
  process.exit(1);
}

console.log(`EDPA root: ${edpaRoot}`);

const app = express();
app.use(cors());
app.use(express.json());

// API routes
app.use('/api/backlog', backlogRoutes(edpaRoot));
app.use('/api/people', peopleRoutes(edpaRoot));
app.use('/api/config', configRoutes(edpaRoot));
app.use('/api/git', gitRoutes(edpaRoot));

// In production, serve the built frontend
if (isProd) {
  const distPath = path.join(import.meta.dirname, '..', 'dist');
  app.use(express.static(distPath));
  app.get('*', (_req, res) => {
    res.sendFile(path.join(distPath, 'index.html'));
  });
}

app.listen(PORT, () => {
  console.log(`PI Planning server running at http://localhost:${PORT}`);
  if (!isProd) console.log('Waiting for Vite dev server on http://localhost:5173');
});
