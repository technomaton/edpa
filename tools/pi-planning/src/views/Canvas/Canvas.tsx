import { useMemo, useRef, useEffect } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import { SectionFrame } from './SectionFrame';

// -- Layout constants ---------------------------------------------------------

const SECTION_GAP = 60;
const PORTFOLIO_W = 2400;
const PORTFOLIO_H = 1400;
const INITIATIVE_KANBAN_W = 2200;
const INITIATIVE_KANBAN_H = 500;
const EPIC_KANBAN_W = 2200;
const EPIC_KANBAN_H = 700;
const FEATURE_KANBAN_W = 2200;
const FEATURE_KANBAN_H = 700;
const PROGRAM_BOARD_W = 2200;
const PROGRAM_BOARD_H = 1200;
const TEAM_SECTION_W = 1000;
const TEAM_SECTION_H = 900;
const ROAM_W = 800;
const ROAM_H = 500;
const PRIO_W = 900;
const PRIO_H = 500;
const CALENDAR_W = 1800;
const CALENDAR_H = 600;

const nodeTypes = {
  sectionFrame: SectionFrame,
};

// -- Section positions --------------------------------------------------------

interface SectionDef {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  component: string;
}

function computeSections(teamIds: string[]): SectionDef[] {
  const sections: SectionDef[] = [];
  let curY = 0;

  // Portfolio Dashboard — top
  sections.push({
    id: 'portfolio-dashboard',
    label: 'Portfolio Dashboard',
    x: 0, y: curY,
    width: PORTFOLIO_W, height: PORTFOLIO_H,
    color: '#db2777',
    component: 'portfolioDashboard',
  });
  curY += PORTFOLIO_H + SECTION_GAP;

  // Initiative Kanban
  sections.push({
    id: 'initiative-kanban',
    label: 'Initiative Kanban',
    x: 0, y: curY,
    width: INITIATIVE_KANBAN_W, height: INITIATIVE_KANBAN_H,
    color: '#db2777',
    component: 'initiativeKanban',
  });
  curY += INITIATIVE_KANBAN_H + SECTION_GAP;

  // Epic Kanban
  sections.push({
    id: 'epic-kanban',
    label: 'Epic Kanban',
    x: 0, y: curY,
    width: EPIC_KANBAN_W, height: EPIC_KANBAN_H,
    color: '#6366f1',
    component: 'epicKanban',
  });
  curY += EPIC_KANBAN_H + SECTION_GAP;

  // Feature Kanban
  sections.push({
    id: 'feature-kanban',
    label: 'Feature Kanban',
    x: 0, y: curY,
    width: FEATURE_KANBAN_W, height: FEATURE_KANBAN_H,
    color: '#0891b2',
    component: 'featureKanban',
  });
  curY += FEATURE_KANBAN_H + SECTION_GAP;

  // Program Board
  sections.push({
    id: 'program-board',
    label: 'Program Board',
    x: 0, y: curY,
    width: PROGRAM_BOARD_W, height: PROGRAM_BOARD_H,
    color: '#6366f1',
    component: 'programBoard',
  });
  curY += PROGRAM_BOARD_H + SECTION_GAP;

  // Team sections — below program board, side by side
  const teamY = curY;
  teamIds.forEach((teamId, idx) => {
    sections.push({
      id: `team-${teamId}`,
      label: `Team: ${teamId}`,
      x: idx * (TEAM_SECTION_W + SECTION_GAP),
      y: teamY,
      width: TEAM_SECTION_W, height: TEAM_SECTION_H,
      color: '#0891b2',
      component: 'team',
    });
  });

  // ROAM + Prioritization — below teams
  const bottomY = teamY + TEAM_SECTION_H + SECTION_GAP;
  sections.push({
    id: 'roam',
    label: 'ROAM Board',
    x: 0, y: bottomY,
    width: ROAM_W, height: ROAM_H,
    color: '#dc2626',
    component: 'roam',
  });

  sections.push({
    id: 'prioritization',
    label: 'WSJF Prioritization',
    x: ROAM_W + SECTION_GAP, y: bottomY,
    width: PRIO_W, height: PRIO_H,
    color: '#d97706',
    component: 'prioritization',
  });

  // Calendar — bottom
  const calY = bottomY + Math.max(ROAM_H, PRIO_H) + SECTION_GAP;
  sections.push({
    id: 'calendar',
    label: 'PI Calendar',
    x: 0, y: calY,
    width: CALENDAR_W, height: CALENDAR_H,
    color: '#059669',
    component: 'calendar',
  });

  return sections;
}

// -- Main Component -----------------------------------------------------------

export function Canvas() {
  const items = useBacklogStore(s => s.items);
  const pi = useConfigStore(s => s.currentPI());
  const pis = useConfigStore(s => s.pis);
  const people = useConfigStore(s => s.people);
  const teams = useConfigStore(s => s.teams);
  const project = useConfigStore(s => s.project);
  const selectedPI = useConfigStore(s => s.selectedPI);
  const isReadonly = useConfigStore(s => s.isReadonly);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rfInstanceRef = useRef<any>(null);

  const allTeamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);

  const sections = useMemo(() => computeSections(allTeamIds), [allTeamIds]);

  // Build section bounds map for sidebar zoom
  const sectionBounds = useMemo(() => {
    const map: Record<string, { x: number; y: number; width: number; height: number }> = {};
    sections.forEach(s => {
      map[s.id] = { x: s.x, y: s.y, width: s.width, height: s.height };
    });
    return map;
  }, [sections]);

  // Expose zoomTo for sidebar
  useEffect(() => {
    (window as unknown as Record<string, unknown>).__piCanvasZoomTo = (sectionId: string) => {
      const bounds = sectionBounds[sectionId];
      if (bounds && rfInstanceRef.current) {
        rfInstanceRef.current.fitBounds(bounds, { padding: 0.1, duration: 500 });
      }
    };
    return () => {
      delete (window as unknown as Record<string, unknown>).__piCanvasZoomTo;
    };
  }, [sectionBounds]);

  const nodes: Node[] = useMemo(() => {
    return sections.map(s => ({
      id: s.id,
      type: 'sectionFrame',
      position: { x: s.x, y: s.y },
      data: {
        label: s.label,
        color: s.color,
        width: s.width,
        height: s.height,
        component: s.component,
        teamId: s.id.startsWith('team-') ? s.id.replace('team-', '') : undefined,
        items, pi, pis, people, teams, project, selectedPI, isReadonly,
      },
      draggable: true,
      selectable: true,
      style: { width: s.width },
    }));
  }, [sections, items, pi, pis, people, teams, project, selectedPI, isReadonly]);

  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(nodes);

  useEffect(() => { setFlowNodes(nodes); }, [nodes, setFlowNodes]);

  return (
    <div className="canvas-container">
      <ReactFlow
        nodes={flowNodes}
        edges={[]}
        onNodesChange={onNodesChange}
        nodeTypes={nodeTypes}
        onInit={(instance) => { rfInstanceRef.current = instance; }}
        fitView
        fitViewOptions={{ padding: 0.05 }}
        minZoom={0.05}
        maxZoom={2}
        panOnScroll
        defaultViewport={{ x: 0, y: 0, zoom: 0.3 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#c0c4cc" />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const color = node.data?.color as string;
            return color || '#ddd';
          }}
          maskColor="rgba(0,0,0,0.05)"
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}
