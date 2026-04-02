import { ProgramBoard } from '../../ProgramBoard/ProgramBoard';

interface Props {
  items: unknown[];
  pi: unknown;
  people: unknown[];
  teams: unknown[];
  isReadonly: boolean;
  width: number;
  height: number;
}

export function ProgramBoardSection({ width, height }: Props) {
  // ProgramBoard reads from stores directly — just give it dimensions
  return (
    <div style={{ width, height: Math.max(height, 800) }}>
      <ProgramBoard />
    </div>
  );
}
