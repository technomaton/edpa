import { useMemo, useState, useCallback, useEffect } from 'react';
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

const COL_W = 300;
const ROW_H = 280;
const HEADER_H = 80;
const ROW_HEADER_W = 140;
const CARD_W = 260;
const CARD_H = 90;
const CARD_GAP = 8;
const CARD_PAD = 12;

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
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const features = items.filter(i => i.type === 'Feature' || i.type === 'Epic');

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
        label: iter.id.split('.').pop() || iter.id,
        sublabel: iter.dates,
        badge: iter.type || undefined,
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
    nodes.push({
      id: `row-${teamId}`,
      type: 'headerNode',
      position: { x: 0, y: HEADER_H + rowIdx * ROW_H },
      data: {
        label: teamId,
        sublabel: `${memberCount} members`,
        variant: 'row',
      },
      draggable: false,
      selectable: false,
      style: { width: ROW_HEADER_W - 4, height: ROW_H - 4 },
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
        position: { x: ROW_HEADER_W + colIdx * COL_W, y: HEADER_H + rowIdx * ROW_H },
        data: {
          teamId,
          iterationId: iter.id,
          used,
          available,
          isActive: iter.status === 'active',
          isDropTarget: dropTarget === cellId,
        },
        draggable: false,
        selectable: false,
        style: { width: COL_W - 4, height: ROW_H - 4, zIndex: -1 },
      });
    });
  });

  // Feature cards
  const cellCount: Record<string, number> = {};

  features.forEach(item => {
    const iterId = iterationForItem(item, iterations);
    const colIdx = iterId ? iterations.findIndex(it => it.id === iterId) : -1;
    const team = getTeamForItem(item, personTeam);
    const rowIdx = teamIds.indexOf(team);

    let x: number, y: number;

    if (colIdx >= 0 && rowIdx >= 0) {
      const cellKey = `${colIdx}-${rowIdx}`;
      const stackIdx = cellCount[cellKey] || 0;
      cellCount[cellKey] = stackIdx + 1;
      x = ROW_HEADER_W + colIdx * COL_W + CARD_PAD;
      y = HEADER_H + rowIdx * ROW_H + CARD_PAD + stackIdx * (CARD_H + CARD_GAP);
    } else {
      // Unassigned — place below grid
      const unIdx = cellCount['unassigned'] || 0;
      cellCount['unassigned'] = unIdx + 1;
      const cols = Math.floor((iterations.length * COL_W) / (CARD_W + CARD_GAP));
      const uCol = unIdx % Math.max(1, cols);
      const uRow = Math.floor(unIdx / Math.max(1, cols));
      x = ROW_HEADER_W + uCol * (CARD_W + CARD_GAP);
      y = HEADER_H + teamIds.length * ROW_H + 60 + uRow * (CARD_H + CARD_GAP);
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
      position: { x: 0, y: HEADER_H + teamIds.length * ROW_H + 20 },
      data: { label: `Backlog (${unassignedCount})`, variant: 'row' },
      draggable: false,
      selectable: false,
      style: { width: ROW_HEADER_W - 4, height: 36 },
    });
  }

  return { nodes, edges };
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

  const { builtNodes, builtEdges } = useMemo(
    () => {
      const { nodes, edges } = buildBoard(
        items, iterations, teamIds, people, personTeam, planningFactors, setSelectedItem, dropTarget,
      );
      return { builtNodes: nodes, builtEdges: edges };
    },
    [items, iterations, teamIds, people, personTeam, planningFactors, dropTarget],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(builtNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(builtEdges);

  // Sync when data changes
  useEffect(() => { setNodes(builtNodes); }, [builtNodes, setNodes]);
  useEffect(() => { setEdges(builtEdges); }, [builtEdges, setEdges]);

  // Highlight target cell during drag
  const onNodeDrag = useCallback(
    (_: unknown, node: Node) => {
      if (node.type !== 'featureCard') return;
      const colIdx = Math.max(0, Math.min(
        iterations.length - 1,
        Math.round((node.position.x - ROW_HEADER_W) / COL_W),
      ));
      const rowIdx = Math.max(0, Math.min(
        teamIds.length - 1,
        Math.round((node.position.y - HEADER_H) / ROW_H),
      ));
      const cellId = `cell-${teamIds[rowIdx]}-${iterations[colIdx]?.id}`;
      setDropTarget(prev => prev === cellId ? prev : cellId);
    },
    [iterations, teamIds],
  );

  // Snap to cell on drag stop
  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      setDropTarget(null);
      if (node.type !== 'featureCard') return;
      const item = node.data.item as WorkItem;

      const colIdx = Math.max(0, Math.min(
        iterations.length - 1,
        Math.round((node.position.x - ROW_HEADER_W) / COL_W),
      ));
      const newIteration = iterations[colIdx]?.id;

      if (newIteration && newIteration !== item.iteration) {
        updateItem(item.id, { iteration: newIteration });
        saveItem(item.id);
      }
    },
    [iterations, updateItem, saveItem],
  );

  // Connect edges (draw new dependency)
  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (connection.source && connection.target) {
        setEdges((eds) => addEdge({
          ...connection,
          animated: true,
          style: { stroke: '#6366f1', strokeWidth: 2 },
          type: 'smoothstep',
        }, eds));
        // TODO: persist depends_on to YAML
      }
    },
    [setEdges],
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
