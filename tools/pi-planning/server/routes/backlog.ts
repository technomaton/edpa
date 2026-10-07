import { Router } from 'express';
import { loadAllItems, loadItem, saveItem, nextId } from '../yaml-store.js';

export function backlogRoutes(edpaRoot: string): Router {
  const router = Router();

  router.get('/', (_req, res) => {
    const items = loadAllItems(edpaRoot);
    res.json({ items });
  });

  router.get('/:type/:id', (req, res) => {
    const item = loadItem(edpaRoot, req.params.id);
    if (!item) return res.status(404).json({ error: 'Not found' });
    res.json(item);
  });

  router.put('/:type/:id', (req, res) => {
    const existing = loadItem(edpaRoot, req.params.id);
    if (!existing) return res.status(404).json({ error: 'Not found' });

    const updated = { ...existing, ...req.body, id: existing.id, type: existing.type };
    saveItem(edpaRoot, updated);
    res.json(updated);
  });

  router.post('/:type', (req, res) => {
    const type = req.params.type;
    const typeMap: Record<string, string> = {
      initiatives: 'Initiative',
      epics: 'Epic',
      features: 'Feature',
      stories: 'Story',
      defects: 'Defect',
      events: 'Event',
      risks: 'Risk',
    };
    const itemType = typeMap[type];
    if (!itemType) return res.status(400).json({ error: `Unknown type: ${type}` });

    let id: string;
    try {
      id = nextId(edpaRoot, itemType, typeof req.body?.title === 'string' ? req.body.title : undefined);
    } catch (e) {
      // e.g. the ID ledger is unreachable — nothing was written.
      return res.status(503).json({ error: (e as Error).message });
    }
    const item = { ...req.body, id, type: itemType };
    saveItem(edpaRoot, item);
    res.status(201).json(item);
  });

  return router;
}
