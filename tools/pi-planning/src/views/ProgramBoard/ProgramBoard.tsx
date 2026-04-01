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
import type { WorkItem, Person, Iteration } from '../../types/edpa';

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

function buildBoard(
  items: WorkItem[],
  iterations: Iteration[],
  teamIds: string[],
  people: Person[],
  personTeam: Record<string, string>,
  planningFactors: Record<string, number>,
  onSelectItem: (item: WorkItem) => void,
  dropTarget: string | null,
): { nodes: Node[]; edges: Edge[]; rowYOffsets: Record<string, number>; rowHeights: Record<string, number> } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Only show Features/Stories on the board (Epics span PIs, not iterations)
  const allFeatures = items.filter(i => i.type === 'Feature' || i.type === 'Story');
  // Filter to items belonging to this PI's iterations or unassigned
  const iterationIds = new Set(iterations.map(it => it.id));
  const features = allFeatures.filter(i => {
    if (!i.iteration) return true; // unassigned — show in backlog
    return iterationIds.has(i.iteration) || iterations.some(it => i.iteration!.startsWith(it.id));
  });

  // Pre-compute items per half-cell to determine dynamic row heights
  const halfCellCounts: Record<string, number> = {};
  features.forEach(item => {
    const iterId = iterationForItem(item, iterations);
    const team = getTeamForItem(item, personTeam);
    if (iterId && teamIds.includes(team)) {
      const half = item.iteration_half || 1;
      const key = `${team}::${iterId}::W${half}`;
      halfCellCounts[key] = (halfCellCounts[key] || 0) + 1;
    }
  });

  // Max items in any half-cell per team row → dynamic row height
  const rowHeights: Record<string, number> = {};
  const rowYOffsets: Record<string, number> = {};
  let yAccum = HEADER_H;
  teamIds.forEach(teamId => {
    let maxInRow = 1;
    iterations.forEach(iter => {
      const w1 = halfCellCounts[`${teamId}::${iter.id}::W1`] || 0;
      const w2 = halfCellCounts[`${teamId}::${iter.id}::W2`] || 0;
      const maxInCell = Math.max(w1, w2);
      if (maxInCell > maxInRow) maxInRow = maxInCell;
    });
    const h = Math.max(ROW_H, CARD_PAD * 2 + 24 + maxInRow * (CARD_H + CARD_GAP));
    rowHeights[teamId] = h;
    rowYOffsets[teamId] = yAccum;
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
        label: iter.id,
        sublabel: iter.dates,
        variant: 'column',
        status: iter.status,
      },
      draggable: false,
      selectable: false,
      style: { width: COL_W - 4, height: HEADER_H - 4 },
    });
  });

  // Row headers (teams) + cells
  teamIds.forEach((teamId, rowIdx) => {
    const memberCount = people.filter(p => p.team === teamId).length;
    const rowH = rowHeights[teamId];
    const rowY = rowYOffsets[teamId];
    nodes.push({
      id: `row-${teamId}`,
      type: 'headerNode',
      position: { x: 0, y: rowY },
      data: {
        label: teamId,
        sublabel: `${memberCount} members`,
        variant: 'row',
      },
      draggable: false,
      selectable: false,
      style: { width: ROW_HEADER_W - 4, height: rowH - 4 },
    });

    iterations.forEach((iter, colIdx) => {
      // Capacity calc
      const teamPeople = people.filter(p => p.team === teamId);
      const available = teamPeople.reduce((s, p) => s + p.capacity, 0) * (planningFactors[teamId] || 0.8);
      const cellFeatures = features.filter(
        f => getTeamForItem(f, personTeam) === teamId &&
             iterationForItem(f, iterations) === iter.id,
      );
      const used = cellFeatures.reduce((s, f) => s + (f.js || 0), 0);

      const cellId = `cell-${teamId}-${iter.id}`;
      nodes.push({
        id: cellId,
        type: 'cellNode',
        position: { x: ROW_HEADER_W + colIdx * COL_W, y: rowY },
        data: {
          teamId,
          iterationId: iter.id,
          used,
          available,
          isActive: iter.status === 'active',
          dropHalf: dropTarget === `${cellId}-W1` ? 1 : dropTarget === `${cellId}-W2` ? 2 : 0,
        },
        draggable: false,
        selectable: false,
        style: { width: COL_W - 4, height: rowH - 4, zIndex: -1 },
      });
    });
  });

  // Feature cards — positioned in W1 or W2 half of each cell
  const halfCount: Record<string, number> = {};

  features.forEach(item => {
    const iterId = iterationForItem(item, iterations);
    const colIdx = iterId ? iterations.findIndex(it => it.id === iterId) : -1;
    const team = getTeamForItem(item, personTeam);
    const rowIdx = teamIds.indexOf(team);
    const half = item.iteration_half || 1;

    let x: number, y: number;

    if (colIdx >= 0 && rowIdx >= 0) {
      const halfKey = `${colIdx}-${rowIdx}-W${half}`;
      const stackIdx = halfCount[halfKey] || 0;
      halfCount[halfKey] = stackIdx + 1;
      const cellX = ROW_HEADER_W + colIdx * COL_W;
      x = cellX + (half === 2 ? HALF_W : 0) + CARD_PAD;
      y = rowYOffsets[team] + 24 + CARD_PAD + stackIdx * (CARD_H + CARD_GAP);
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

    nodes.push({
      id: item.id,
      type: 'featureCard',
      position: { x, y },
      data: { item, onSelect: onSelectItem },
      style: { width: CARD_W, zIndex: 10 },
    });

    // Dependency edges
    if (item.depends_on) {
      item.depends_on.forEach(depId => {
        edges.push({
          id: `dep-${depId}-${item.id}`,
          source: depId,
          target: item.id,
          animated: true,
          style: { stroke: '#6366f1', strokeWidth: 2 },
          type: 'smoothstep',
        });
      });
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

  return { nodes, edges, rowYOffsets, rowHeights };
}

// -- Detail Panel (overlay) ---------------------------------------------------

function DetailPanel({ item, onClose }: { item: WorkItem; onClose: () => void }) {
  const TYPE_FG: Record<string, string> = {
    Initiative: '#db2777', Epic: '#6366f1', Feature: '#0891b2',
    Story: '#ea580c', Defect: '#dc2626',
  };
  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <span className="detail-panel__id" style={{ color: TYPE_FG[item.type] }}>{item.id}</span>
        <button className="detail-panel__close" onClick={onClose}>X</button>
      </div>
      <h3 className="detail-panel__title">{item.title}</h3>
      <div className="detail-panel__grid">
        {[
          ['Type', item.type],
          ['Status', item.status],
          ['Iteration', item.iteration || '-'],
          ['Owner', item.owner || item.assignee || '-'],
          ['Job Size', String(item.js ?? '-')],
          ['WSJF', item.wsjf?.toFixed(2) ?? '-'],
          ...(item.bv != null ? [['BV / TC / RR', `${item.bv} / ${item.tc} / ${item.rr}`]] : []),
          ['Parent', item.parent || '-'],
        ].map(([label, value]) => (
          <div key={label} className="detail-field">
            <span className="detail-field__label">{label}</span>
            <span className="detail-field__value">{value}</span>
          </div>
        ))}
      </div>
      {item.contributors && item.contributors.length > 0 && (
        <div className="detail-panel__contributors">
          <span className="detail-field__label">Contributors</span>
          {item.contributors.map((c, i) => (
            <div key={i} className="detail-contributor">
              <span>{c.person}</span>
              <span className="detail-contributor__role">{c.role}</span>
              <span className="detail-contributor__cw">CW {c.cw}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
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
  const [dropTarget, setDropTarget] = useState<string | null>(null); // "cell-TEAM-ITER"

  const iterations = pi?.iterations || [];
  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
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

  const { builtNodes, builtEdges } = useMemo(
    () => {
      const { nodes, edges, rowYOffsets: ryo, rowHeights: rh } = buildBoard(
        items, iterations, teamIds, people, personTeam, planningFactors, setSelectedItem, dropTarget,
      );
      layoutRef.current = { rowYOffsets: ryo, rowHeights: rh };
      return { builtNodes: nodes, builtEdges: edges };
    },
    [items, iterations, teamIds, people, personTeam, planningFactors, dropTarget],
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
      let matchedTeam = teamIds[0];
      for (const tid of teamIds) {
        const rowTop = ryo[tid] || 0;
        const rowBot = rowTop + (rh[tid] || ROW_H);
        if (centerY >= rowTop && centerY < rowBot) {
          matchedTeam = tid;
          break;
        }
      }
      const xInCell = centerX - (ROW_HEADER_W + colIdx * COL_W);
      const half: 1 | 2 = xInCell < HALF_W ? 1 : 2;
      return { colIdx, team: matchedTeam, half, iteration: iterations[colIdx]?.id };
    },
    [iterations, teamIds],
  );

  // Highlight target half-cell during drag
  const onNodeDrag = useCallback(
    (_: unknown, node: Node) => {
      if (node.type !== 'featureCard') return;
      const { team, iteration, half } = detectCellHalf(node.position.x, node.position.y);
      const targetId = `cell-${team}-${iteration}-W${half}`;
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
      const { iteration, half } = detectCellHalf(node.position.x, node.position.y);

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
      <ReactFlow
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
        <DetailPanel item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </div>
  );
}
