import { Router } from 'express';
import { createGitClient } from '../git.js';

export function gitRoutes(edpaRoot: string): Router {
  const router = Router();
  const git = createGitClient(edpaRoot);

  router.get('/status', async (_req, res) => {
    const status = await git.status();
    res.json(status);
  });

  router.post('/commit', async (req, res) => {
    const { message } = req.body;
    if (!message) return res.status(400).json({ error: 'message required' });
    const hash = await git.commit(message);
    res.json({ hash });
  });

  router.post('/branch', async (req, res) => {
    const { name } = req.body;
    if (!name) return res.status(400).json({ error: 'name required' });
    const branch = await git.createBranch(name);
    res.json({ branch });
  });

  router.get('/branches', async (_req, res) => {
    const branches = await git.branches();
    res.json({ branches });
  });

  return router;
}
