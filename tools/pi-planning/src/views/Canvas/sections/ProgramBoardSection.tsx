import { ReactFlowProvider } from '@xyflow/react';
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
  // ProgramBoard needs its own ReactFlowProvider to isolate node types
  // from the parent canvas ReactFlow context
  return (
    <div style={{ width, height: Math.max(height, 800) }}>
      <ReactFlowProvider>
        <ProgramBoard />
      </ReactFlowProvider>
    </div>
  );
}
