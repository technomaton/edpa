import { Router } from 'express';
import { loadPeopleConfig } from '../yaml-store.js';

export function peopleRoutes(edpaRoot: string): Router {
  const router = Router();

  router.get('/', (_req, res) => {
    const data = loadPeopleConfig(edpaRoot);
    res.json(data);
  });

  return router;
}
