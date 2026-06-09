import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type OnConnect,
  addEdge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import { FeatureCard } from './FeatureCard';
import { CellNode } from './CellNode';
import { HeaderNode } from './HeaderNode';
import { ItemEditor } from '../../components/ItemEditor';
import type { WorkItem, Person, Iteration, PIEvent } from '../../types/edpa';

// -- Layout constants ---------------------------------------------------------

const COL_W = 400;
const HALF_W = COL_W / 2;
const ROW_H = 280;
const HEADER_H = 80;
const ROW_HEADER_W = 140;
const CARD_W = HALF_W - 24;  // fit in half-cell with padding
const CARD_H = 90;
const CARD_GAP = 8;
const CARD_PAD = 8;

const nodeTypes = {
  featureCard: FeatureCard,
  cellNode: CellNode,
  headerNode: HeaderNode,
};

// -- Helpers ------------------------------------------------------------------

function getTeamForItem(item: WorkItem, personTeam: Record<string, string>): string {
  return personTeam[item.owner || ''] || personTeam[item.assignee || ''] || 'Unassigned';
}

function iterationForItem(item: WorkItem, iterations: Iteration[]): string | null {
  if (!item.iteration) return null;
  const match = iterations.find(it => item.iteration!.startsWith(it.id));
  return match?.id || null;
}

// -- Build nodes & edges ------------------------------------------------------

interface BoardFilter {
  team: string;
  status: string;
  text: string;
}

function matchesFilter(item: WorkItem, f: BoardFilter, personTeam: Record<string, string>): boolean {
  if (f.team && getTeamForItem(item, personTeam) !== f.team) return false;
  if (f.status && (item.status || '').toLowerCase() !== f.status.toLowerCase()) return false;
  if (f.text) {
    const t = f.text.toLowerCase();
    if (!item.id.toLowerCase().includes(t) && !(item.title || '').toLowerCase().includes(t)) return false;
  }
  return true;
}

function buildBoard(
  items: WorkItem[],
  iterations: Iteration[],
  internalTeamIds: string[],
  externalTeamIds: string[],
  people: Person[],
  personTeam: Record<string, string>,
  planningFactors: Record<string, number>,
  piEvents: PIEvent[],
  pi_iteration_weeks: number,
  onSelectItem: (item: WorkItem) => void,
  dropTarget: string | null,
  boardFilter: BoardFilter,
): { nodes: Node[]; edges: Edge[]; rowYOffsets: Record<string, number>; rowHeights: Record<string, number>; backwardDeps: number; sameIterCrossTeam: number } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // All team IDs in order: events row + internal + external
  const allRowIds = ['__events__', ...internalTeamIds, ...externalTeamIds];

  // Filter items for this PI
  const iterationIds = new Set(iterations.map(it => it.id));
  const piItems = items.filter(i => {
    if (!i.iteration) return true;
    return iterationIds.has(i.iteration) || iterations.some(it => i.iteration!.startsWith(it.id));
  });

  // Events from backlog
  const backlogEvents = piItems.filter(i => i.type === 'Event');
  // Synthetic events from PI events config
  // Only show events that have an iteration within this PI.
  // Events without iteration (e.g. PI Planning) happen in the *previous* PI's
  // IP iteration, so they don't belong on this PI's board.
  const syntheticEvents: WorkItem[] = piEvents
    .filter(evt => evt.iteration && iterationIds.has(evt.iteration))
    .map((evt, i) => ({
      id: `EVT-${i + 1}`,
      type: 'Event' as const,
      title: evt.title,
      js: 0,
      status: 'Planned' as const,
      parent: null,
      iteration: evt.iteration,
      contributors: [],
    }));
  const events = [...backlogEvents, ...syntheticEvents];
  // Features/Stories for the board (filtered by boardFilter)
  const allFeatures = piItems.filter(i => i.type === 'Feature' || i.type === 'Story');
  const hasFilter = boardFilter.team || boardFilter.status || boardFilter.text;
  const features = hasFilter
    ? allFeatures.filter(f => matchesFilter(f, boardFilter, personTeam))
    : allFeatures;

  // Child story rollup per feature (done/total/totalJS from ALL backlog stories, not just PI)
  const DONE_STATUSES = new Set(['done', 'closed', 'accepted', 'complete', 'completed']);
  const childRollup = new Map<string, { done: number; total: number; totalJS: number }>();
  items.filter(i => i.type === 'Story' && i.parent).forEach(story => {
    const fid = story.parent!;
    const cur = childRollup.get(fid) || { done: 0, total: 0, totalJS: 0 };
    const isDone = DONE_STATUSES.has((story.status || '').toLowerCase().replace(/[\s-]/g, ''));
    childRollup.set(fid, {
      done: cur.done + (isDone ? 1 : 0),
      total: cur.total + 1,
      totalJS: cur.totalJS + (story.js || 0),
    });
  });

  // Build dependency lookup for color coding
  const hasIncomingDep = new Set<string>();
  const hasOutgoingDep = new Set<string>();
  [...features, ...events].forEach(item => {
    if (item.depends_on) {
      item.depends_on.forEach(depId => {
        hasOutgoingDep.add(depId);
        hasIncomingDep.add(item.id);
      });
    }
  });

  // Pre-compute items per half-cell to determine dynamic row heights
  const halfCellCounts: Record<string, number> = {};
  const allBoardItems = [...features, ...events];
  const teamIds = [...internalTeamIds, ...externalTeamIds];

  allBoardItems.forEach(item => {
    const iterId = iterationForItem(item, iterations);
    const rowId = item.type === 'Event'
      ? '__events__'
      : getTeamForItem(item, personTeam);
    if (iterId && allRowIds.includes(rowId)) {
      const half = item.iteration_half || 1;
      const key = `${rowId}::${iterId}::W${half}`;
      halfCellCounts[key] = (halfCellCounts[key] || 0) + 1;
    }
  });

  // Dynamic row heights for all rows (events + internal + external)
  const EVENTS_ROW_MIN_H = 120;
  const rowHeights: Record<string, number> = {};
  const rowYOffsets: Record<string, number> = {};
  let yAccum = HEADER_H;

  allRowIds.forEach(rowId => {
    let maxInRow = 1;
    iterations.forEach(iter => {
      const w1 = halfCellCounts[`${rowId}::${iter.id}::W1`] || 0;
      const w2 = halfCellCounts[`${rowId}::${iter.id}::W2`] || 0;
      const maxInCell = Math.max(w1, w2);
      if (maxInCell > maxInRow) maxInRow = maxInCell;
    });
    const minH = rowId === '__events__' ? EVENTS_ROW_MIN_H : ROW_H;
    const h = Math.max(minH, CARD_PAD * 2 + 24 + maxInRow * (CARD_H + CARD_GAP));
    rowHeights[rowId] = h;
    rowYOffsets[rowId] = yAccum;
    yAccum += h;
  });
  const totalGridHeight = yAccum;

  // Corner node
  nodes.push({
    id: 'corner',
    type: 'headerNode',
    position: { x: 0, y: 0 },
    data: { label: 'Team / Iteration', variant: 'corner' },
    draggable: false,
    selectable: false,
    style: { width: ROW_HEADER_W - 4, height: HEADER_H - 4 },
  });

  // Column headers (iterations)
  iterations.forEach((iter, colIdx) => {
    nodes.push({
      id: `col-${iter.id}`,
      type: 'headerNode',
      position: { x: ROW_HEADER_W + colIdx * COL_W, y: 0 },
      data: {
        label: iter.type ? `${iter.id} (${iter.type})` : iter.id,
        sublabel: iter.dates,
        variant: 'column',
        status: iter.status,
      },
      draggable: false,
      selectable: false,
      style: { width: COL_W - 4, height: HEADER_H - 4 },
    });
  });

  // Row headers + cells for all rows
  allRowIds.forEach((rowId) => {
    const isEventsRow = rowId === '__events__';
    const isExternal = externalTeamIds.includes(rowId);
    const memberCount = isEventsRow ? 0 : people.filter(p => p.team === rowId).length;
    const rowH = rowHeights[rowId];
    const rowY = rowYOffsets[rowId];
    const rowLabel = isEventsRow ? 'Events' : rowId;
    const rowSub = isEventsRow ? '' : isExternal ? `${memberCount} ext` : `${memberCount} members`;
    nodes.push({
      id: `row-${rowId}`,
      type: 'headerNode',
      position: { x: 0, y: rowY },
      data: {
        label: rowLabel,
        sublabel: rowSub,
        variant: isEventsRow ? 'events-row' : isExternal ? 'external-row' : 'row',
      },
      draggable: false,
      selectable: false,
      style: { width: ROW_HEADER_W - 4, height: rowH - 4 },
    });

    iterations.forEach((iter, colIdx) => {
      // Capacity calc (skip for events row)
      const teamPeople = isEventsRow ? [] : people.filter(p => p.team === rowId);
      const available = isEventsRow ? 0 : teamPeople.reduce((s, p) => s + p.capacity, 0) * (planningFactors[rowId] || 0.8);
      const cellItems = isEventsRow
        ? events.filter(m => iterationForItem(m, iterations) === iter.id)
        : features.filter(f => getTeamForItem(f, personTeam) === rowId && iterationForItem(f, iterations) === iter.id);
      const used = cellItems.reduce((s, f) => s + (f.js || 0), 0);

      const cellId = `cell-${rowId}-${iter.id}`;
      nodes.push({
        id: cellId,
        type: 'cellNode',
        position: { x: ROW_HEADER_W + colIdx * COL_W, y: rowY },
        data: {
          teamId: rowId,
          iterationId: iter.id,
          used,
          available,
          isActive: iter.status === 'active',
          isIP: iter.type === 'IP',
          isSingleWeek: (pi_iteration_weeks || 2) <= 1,
          dropHalf: dropTarget === `${cellId}-W1` ? 1 : dropTarget === `${cellId}-W2` ? 2 : 0,
          dropBlocked: dropTarget === `${cellId}-BLOCKED`,
        },
        draggable: false,
        selectable: false,
        style: { width: COL_W - 4, height: rowH - 4, zIndex: -1 },
      });
    });
  });

  // All board cards — features + events
  const halfCount: Record<string, number> = {};

  [...features, ...events].forEach(item => {
    const iterId = iterationForItem(item, iterations);
    const colIdx = iterId ? iterations.findIndex(it => it.id === iterId) : -1;
    const isEvent = item.type === 'Event';
    const rowId = isEvent ? '__events__' : getTeamForItem(item, personTeam);
    const rowIdx = allRowIds.indexOf(rowId);
    const half = item.iteration_half || 1;

    let x: number, y: number;

    if (colIdx >= 0 && rowIdx >= 0) {
      const halfKey = `${colIdx}-${rowIdx}-W${half}`;
      const stackIdx = halfCount[halfKey] || 0;
      halfCount[halfKey] = stackIdx + 1;
      const cellX = ROW_HEADER_W + colIdx * COL_W;
      const singleWeek = (pi_iteration_weeks || 2) <= 1;
      x = cellX + (singleWeek ? 0 : (half === 2 ? HALF_W : 0)) + CARD_PAD;
      y = rowYOffsets[rowId] + 24 + CARD_PAD + stackIdx * (CARD_H + CARD_GAP);
    } else {
      // Unassigned — place below grid
      const unIdx = halfCount['unassigned'] || 0;
      halfCount['unassigned'] = unIdx + 1;
      const cols = Math.floor((iterations.length * COL_W) / (CARD_W + CARD_GAP));
      const uCol = unIdx % Math.max(1, cols);
      const uRow = Math.floor(unIdx / Math.max(1, cols));
      x = ROW_HEADER_W + uCol * (CARD_W + CARD_GAP);
      y = totalGridHeight + 60 + uRow * (CARD_H + CARD_GAP);
    }

    // Color: yellow = event, red = has dependency, blue = independent
    const depColor = isEvent ? 'event'
      : hasIncomingDep.has(item.id) ? 'dependent'
      : 'independent';

    nodes.push({
      id: item.id,
      type: 'featureCard',
      position: { x, y },
      data: { item, onSelect: onSelectItem, depColor, rollup: item.type === 'Feature' ? (childRollup.get(item.id) || null) : null },
      style: { width: (pi_iteration_weeks || 2) <= 1 ? COL_W - 24 : CARD_W, zIndex: 10 },
    });

    // Dependency edges
    if (item.depends_on) {
      item.depends_on.forEach(depId => {
        edges.push({
          id: `dep-${depId}-${item.id}`,
          source: depId,
          target: item.id,
          type: 'smoothstep',
        });
      });
    }
  });

  // Classify edges by conflict type
  let backwardDeps = 0;
  let sameIterCrossTeam = 0;
  const itemById = new Map(allBoardItems.map(i => [i.id, i]));

  edges.forEach(edge => {
    const sourceItem = itemById.get(edge.source);
    const targetItem = itemById.get(edge.target);
    if (!sourceItem || !targetItem) {
      edge.style = { stroke: '#6366f1', strokeWidth: 2 };
      edge.animated = true;
      return;
    }

    const sourceIterIdx = iterations.findIndex(it => sourceItem.iteration?.startsWith(it.id));
    const targetIterIdx = iterations.findIndex(it => targetItem.iteration?.startsWith(it.id));
    const sourceTeam = getTeamForItem(sourceItem, personTeam);
    const targetTeam = getTeamForItem(targetItem, personTeam);

    if (targetIterIdx >= 0 && sourceIterIdx >= 0 && targetIterIdx < sourceIterIdx) {
      // BACKWARD — blocker: target needed before source delivers
      edge.style = { stroke: '#dc2626', strokeWidth: 3 };
      edge.animated = true;
      edge.label = '⚠ BACKWARD';
      edge.labelStyle = { fill: '#dc2626', fontWeight: 700 };
      backwardDeps++;
    } else if (targetIterIdx >= 0 && sourceIterIdx >= 0 && targetIterIdx === sourceIterIdx && sourceTeam !== targetTeam) {
      // SAME ITERATION, CROSS-TEAM — warning
      edge.style = { stroke: '#d97706', strokeWidth: 2, strokeDasharray: '5,5' };
      edge.label = '⚡ same iter';
      edge.labelStyle = { fill: '#d97706' };
      sameIterCrossTeam++;
    } else {
      // Normal forward dependency
      edge.style = { stroke: '#6366f1', strokeWidth: 2 };
      edge.animated = true;
    }
  });

  // Unassigned header (if any)
  const unassignedCount = features.filter(f => iterationForItem(f, iterations) === null).length;
  if (unassignedCount > 0) {
    nodes.push({
      id: 'unassigned-header',
      type: 'headerNode',
      position: { x: 0, y: totalGridHeight + 20 },
      data: { label: `Backlog (${unassignedCount})`, variant: 'row' },
      draggable: false,
      selectable: false,
      style: { width: ROW_HEADER_W - 4, height: 36 },
    });
  }

  return { nodes, edges, rowYOffsets, rowHeights, backwardDeps, sameIterCrossTeam };
}

// -- Main Component -----------------------------------------------------------

export function ProgramBoard() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const pi = useConfigStore(s => s.currentPI());
  const people = useConfigStore(s => s.people);
  const teams = useConfigStore(s => s.teams);
  const isReadonly = useConfigStore(s => s.isReadonly);
  const selectedPI = useConfigStore(s => s.selectedPI);
  const [selectedItem, setSelectedItem] = useState<WorkItem | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [boardFilter, setBoardFilter] = useState<BoardFilter>({ team: '', status: '', text: '' });

  const iterations = pi?.iterations || [];
  const sharedServiceIds = useMemo(() => new Set(pi?.shared_services || []), [pi]);
  const allTeamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
  const internalTeamIds = useMemo(
    () => allTeamIds.filter(t => !sharedServiceIds.has(t) && !teams.find(tm => tm.id === t && tm.type === 'external')),
    [allTeamIds, sharedServiceIds, teams],
  );
  const externalTeamIds = useMemo(
    () => allTeamIds.filter(t => sharedServiceIds.has(t) || teams.find(tm => tm.id === t && tm.type === 'external')),
    [allTeamIds, sharedServiceIds, teams],
  );
  const personTeam = useMemo(() => {
    const m: Record<string, string> = {};
    people.forEach(p => { m[p.id] = p.team; });
    return m;
  }, [people]);
  const planningFactors = useMemo(() => {
    const m: Record<string, number> = {};
    teams.forEach(t => { m[t.id] = t.planning_factor; });
    return m;
  }, [teams]);

  const layoutRef = useRef<{ rowYOffsets: Record<string, number>; rowHeights: Record<string, number> }>({
    rowYOffsets: {}, rowHeights: {},
  });

  const { builtNodes, builtEdges, backwardDeps, sameIterCrossTeam } = useMemo(
    () => {
      const { nodes, edges, rowYOffsets: ryo, rowHeights: rh, backwardDeps: bd, sameIterCrossTeam: si } = buildBoard(
        items, iterations, internalTeamIds, externalTeamIds, people, personTeam, planningFactors, pi?.events || [], pi?.iteration_weeks || 2, setSelectedItem, dropTarget, boardFilter,
      );
      layoutRef.current = { rowYOffsets: ryo, rowHeights: rh };
      return { builtNodes: nodes, builtEdges: edges, backwardDeps: bd, sameIterCrossTeam: si };
    },
    [items, iterations, internalTeamIds, externalTeamIds, people, personTeam, planningFactors, pi, dropTarget, boardFilter],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(builtNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(builtEdges);

  // Sync when data changes
  useEffect(() => { setNodes(builtNodes); }, [builtNodes, setNodes]);
  useEffect(() => { setEdges(builtEdges); }, [builtEdges, setEdges]);

  // Detect which cell + half the node is over (use card center, not left edge)
  const detectCellHalf = useCallback(
    (nodeX: number, nodeY: number) => {
      const centerX = nodeX + CARD_W / 2;
      const centerY = nodeY + CARD_H / 2;
      const colIdx = Math.max(0, Math.min(
        iterations.length - 1,
        Math.floor((centerX - ROW_HEADER_W) / COL_W),
      ));
      const { rowYOffsets: ryo, rowHeights: rh } = layoutRef.current;
      const allRowIds = ['__events__', ...internalTeamIds, ...externalTeamIds];
      let matchedTeam = allRowIds[0];
      for (const tid of allRowIds) {
        const rowTop = ryo[tid] || 0;
        const rowBot = rowTop + (rh[tid] || ROW_H);
        if (centerY >= rowTop && centerY < rowBot) {
          matchedTeam = tid;
          break;
        }
      }
      const xInCell = centerX - (ROW_HEADER_W + colIdx * COL_W);
      const half: 1 | 2 = xInCell < HALF_W ? 1 : 2;
      const iter = iterations[colIdx];
      return { colIdx, team: matchedTeam, half, iteration: iter?.id, isIP: iter?.type === 'IP' };
    },
    [iterations, internalTeamIds, externalTeamIds],
  );

  // Highlight target half-cell during drag
  const onNodeDrag = useCallback(
    (_: unknown, node: Node) => {
      if (node.type !== 'featureCard') return;
      const item = node.data.item as WorkItem;
      const { team, iteration, half, isIP } = detectCellHalf(node.position.x, node.position.y);
      const isEvent = item.type === 'Event';
      // Show blocked indicator for IP iterations (except events)
      const suffix = isIP && !isEvent ? '-BLOCKED' : `-W${half}`;
      const targetId = `cell-${team}-${iteration}${suffix}`;
      setDropTarget(prev => prev === targetId ? prev : targetId);
    },
    [detectCellHalf],
  );

  // Snap to cell on drag stop — save iteration + half
  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      setDropTarget(null);
      if (node.type !== 'featureCard') return;
      const item = node.data.item as WorkItem;
      const { iteration, half, isIP } = detectCellHalf(node.position.x, node.position.y);

      // Block drop into IP iteration (Innovation & Planning — no work planned)
      if (isIP && item.type !== 'Event') {
        setWarning(`IP iteration (${iteration}) is reserved for Innovation & Planning — no work items`);
        setTimeout(() => setWarning(null), 3000);
        return;
      }

      if (iteration && (iteration !== item.iteration || half !== item.iteration_half)) {
        updateItem(item.id, { iteration, iteration_half: half });
        saveItem(item.id);
      }
    },
    [detectCellHalf, updateItem, saveItem],
  );

  // Connect edges (draw new dependency) and persist to YAML
  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (connection.source && connection.target) {
        setEdges((eds) => addEdge({
          ...connection,
          animated: true,
          style: { stroke: '#6366f1', strokeWidth: 2 },
          type: 'smoothstep',
        }, eds));
        // Persist: add target to source's depends_on
        const targetItem = items.find(i => i.id === connection.target);
        if (targetItem) {
          const currentDeps = targetItem.depends_on || [];
          if (!currentDeps.includes(connection.source)) {
            updateItem(connection.target, { depends_on: [...currentDeps, connection.source] });
            saveItem(connection.target);
          }
        }
      }
    },
    [setEdges, items, updateItem, saveItem],
  );

  return (
    <div className="program-board">
      {isReadonly && (
        <div className="readonly-banner">
          {selectedPI} — Closed (read-only)
        </div>
      )}
      {warning && (
        <div className="warning-banner">
          {warning}
        </div>
      )}
      {(backwardDeps > 0 || sameIterCrossTeam > 0) && (
        <div className="conflict-banner">
          {backwardDeps > 0 && (
            <span className="conflict-badge conflict-badge--red">
              {backwardDeps} backward dep{backwardDeps !== 1 ? 's' : ''}
            </span>
          )}
          {sameIterCrossTeam > 0 && (
            <span className="conflict-badge conflict-badge--yellow">
              {sameIterCrossTeam} same-iter cross-team
            </span>
          )}
        </div>
      )}
      <div className="pb-filter-bar">
        <select
          className="pb-filter-select"
          value={boardFilter.team}
          onChange={e => setBoardFilter(f => ({ ...f, team: e.target.value }))}
          title="Filter by team"
        >
          <option value="">All teams</option>
          {[...internalTeamIds, ...externalTeamIds].map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          className="pb-filter-select"
          value={boardFilter.status}
          onChange={e => setBoardFilter(f => ({ ...f, status: e.target.value }))}
          title="Filter by status"
        >
          <option value="">All statuses</option>
          {['Backlog', 'Implementing', 'Validating', 'Done'].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          className="pb-filter-input"
          type="search"
          placeholder="Search ID or title…"
          value={boardFilter.text}
          onChange={e => setBoardFilter(f => ({ ...f, text: e.target.value }))}
        />
        {(boardFilter.team || boardFilter.status || boardFilter.text) && (
          <button
            className="pb-filter-clear"
            onClick={() => setBoardFilter({ team: '', status: '', text: '' })}
            title="Clear filters"
          >
            ✕ clear
          </button>
        )}
      </div>
      <ReactFlow
        style={{ flex: 1 }}
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDrag={isReadonly ? undefined : onNodeDrag}
        onNodeDragStop={isReadonly ? undefined : onNodeDragStop}
        onConnect={isReadonly ? undefined : onConnect}
        nodesDraggable={!isReadonly}
        nodesConnectable={!isReadonly}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.1 }}
        minZoom={0.15}
        maxZoom={2.5}
        snapToGrid
        snapGrid={[10, 10]}
        panOnScroll
        selectionOnDrag={false}
      >
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            if (node.type === 'cellNode') return 'rgba(99,102,241,0.08)';
            if (node.type === 'headerNode') return '#e2e4ea';
            const it = node.data?.item as WorkItem | undefined;
            if (!it) return '#ddd';
            const c: Record<string, string> = {
              Feature: '#0891b2', Epic: '#6366f1', Story: '#ea580c',
              Initiative: '#db2777', Defect: '#dc2626',
            };
            return c[it.type] || '#999';
          }}
          maskColor="rgba(0,0,0,0.05)"
          pannable
          zoomable
        />
      </ReactFlow>

      {selectedItem && (
        <ItemEditor
          item={selectedItem}
          iterations={iterations}
          people={people.map(p => p.id)}
          readonly={isReadonly}
          onClose={() => setSelectedItem(null)}
          onSave={(updated) => {
            updateItem(updated.id, updated);
            saveItem(updated.id);
            setSelectedItem(null);
          }}
        />
      )}
    </div>
  );
}
