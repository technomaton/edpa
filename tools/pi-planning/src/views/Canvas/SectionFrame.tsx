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

  const contentHeight = height - 40;

  return (
    <div
      className="section-frame"
      style={{ width, height, borderColor: color }}
    >
      <div className="section-frame__header" style={{ background: color }}>
        <span className="section-frame__title">{label}</span>
      </div>
      <div className="section-frame__content" style={{ height: contentHeight }}>
        {component === 'programBoard' && (
          <ProgramBoardSection
            items={items} pi={pi} people={people} teams={teams}
            isReadonly={isReadonly}
            width={width} height={contentHeight}
          />
        )}
        {component === 'team' && teamId && (
          <TeamSection
            teamId={teamId}
            items={items} pi={pi} people={people} teams={teams}
            selectedPI={selectedPI}
            isReadonly={isReadonly}
            width={width} height={contentHeight}
          />
        )}
        {component === 'roam' && (
          <RoamSection
            items={items} selectedPI={selectedPI}
            isReadonly={isReadonly}
            width={width} height={contentHeight}
          />
        )}
        {component === 'prioritization' && (
          <PrioritizationSection
            items={items} pi={pi}
            width={width} height={contentHeight}
          />
        )}
        {component === 'calendar' && (
          <CalendarSection
            pis={pis} project={project}
            width={width} height={contentHeight}
          />
        )}
      </div>
    </div>
  );
}

export const SectionFrame = memo(SectionFrameInner);
