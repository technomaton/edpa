import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { ProgramBoardSection } from './sections/ProgramBoardSection';
import { TeamSection } from './sections/TeamSection';
import { RoamSection } from './sections/RoamSection';
import { PrioritizationSection } from './sections/PrioritizationSection';
import { CalendarSection } from './sections/CalendarSection';

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

  // Program Board needs fixed height for nested React Flow
  const needsFixedHeight = component === 'programBoard';

  return (
    <div
      className="section-frame"
      style={{ width, height: needsFixedHeight ? height : undefined, borderColor: color }}
    >
      <div className="section-frame__header" style={{ background: color }}>
        <span className="section-frame__title">{label}</span>
      </div>
      <div className="section-frame__content" style={needsFixedHeight ? { height: height - 40, overflow: 'hidden' } : undefined}>
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
