import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { ProgramBoardSection } from './sections/ProgramBoardSection';
import { TeamSection } from './sections/TeamSection';
import { RoamSection } from './sections/RoamSection';
import { PrioritizationSection } from './sections/PrioritizationSection';
import { CalendarSection } from './sections/CalendarSection';
import { InitiativeKanbanSection } from './sections/InitiativeKanbanSection';
import { EpicKanbanSection } from './sections/EpicKanbanSection';
import { FeatureKanbanSection } from './sections/FeatureKanbanSection';
import { PortfolioDashboardSection } from './sections/PortfolioDashboardSection';

function SectionFrameInner({ data }: NodeProps) {
  const {
    label, color, width, height, component, teamId,
    items, pi, pis, people, teams, project, selectedPI, isReadonly,
  } = data as {
    label: string;
    color: string;
    width: number;
    height: number;
    component: string;
    teamId?: string;
    items: unknown[];
    pi: unknown;
    pis: unknown[];
    people: unknown[];
    teams: unknown[];
    project: unknown;
    selectedPI: string | null;
    isReadonly: boolean;
  };

  return (
    <div
      className="section-frame"
      style={{ width, borderColor: color }}
    >
      <div className="section-frame__header" style={{ background: color }}>
        <span className="section-frame__title">{label}</span>
      </div>
      <div className="section-frame__content">
        {component === 'portfolioDashboard' && (
          <PortfolioDashboardSection
            items={items} people={people} project={project}
            width={width} height={height - 40}
          />
        )}
        {component === 'initiativeKanban' && (
          <InitiativeKanbanSection
            items={items} isReadonly={isReadonly}
            width={width} height={height - 40}
          />
        )}
        {component === 'epicKanban' && (
          <EpicKanbanSection
            items={items} isReadonly={isReadonly}
            width={width} height={height - 40}
          />
        )}
        {component === 'featureKanban' && (
          <FeatureKanbanSection
            items={items} selectedPI={selectedPI}
            isReadonly={isReadonly}
            width={width} height={height - 40}
          />
        )}
        {component === 'programBoard' && (
          <ProgramBoardSection
            items={items} pi={pi} people={people} teams={teams}
            isReadonly={isReadonly}
            width={width} height={height - 40}
          />
        )}
        {component === 'team' && teamId && (
          <TeamSection
            teamId={teamId}
            items={items} pi={pi} people={people} teams={teams}
            selectedPI={selectedPI}
            isReadonly={isReadonly}
            width={width} height={height}
          />
        )}
        {component === 'roam' && (
          <RoamSection
            items={items} selectedPI={selectedPI}
            isReadonly={isReadonly}
            width={width} height={height}
          />
        )}
        {component === 'prioritization' && (
          <PrioritizationSection
            items={items} pi={pi}
            width={width} height={height}
          />
        )}
        {component === 'calendar' && (
          <CalendarSection
            pis={pis} project={project}
            width={width} height={height}
          />
        )}
      </div>
    </div>
  );
}

export const SectionFrame = memo(SectionFrameInner);
