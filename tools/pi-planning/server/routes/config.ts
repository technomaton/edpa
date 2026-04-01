import { Router } from 'express';
import { loadEdpaConfig, loadPeopleConfig } from '../yaml-store.js';

export function configRoutes(edpaRoot: string): Router {
  const router = Router();

  router.get('/', (_req, res) => {
    const edpa = loadEdpaConfig(edpaRoot);
    const { project } = loadPeopleConfig(edpaRoot);
    res.json({ ...edpa, project });
  });

  return router;
}
