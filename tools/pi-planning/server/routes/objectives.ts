import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';

export function objectivesRoutes(edpaRoot: string): Router {
  const router = Router();

  function objectivesPath(piId: string): string {
    return path.join(edpaRoot, '.edpa', 'pi-objectives', `${piId}.yaml`);
  }

  router.get('/:piId', (req, res) => {
    const filePath = objectivesPath(req.params.piId);
    try {
      const data = yaml.load(fs.readFileSync(filePath, 'utf-8'));
      res.json(data);
    } catch {
      res.json({ pi: req.params.piId, teams: {} });
    }
  });

  router.put('/:piId', (req, res) => {
    const filePath = objectivesPath(req.params.piId);
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const content = yaml.dump(req.body, { lineWidth: 120, noRefs: true, sortKeys: false });
    fs.writeFileSync(filePath, content, 'utf-8');
    res.json(req.body);
  });

  return router;
}
