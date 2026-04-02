import { Calendar } from '../../Calendar/Calendar';

interface Props {
  pis: unknown[];
  project: unknown;
  width: number;
  height: number;
}

export function CalendarSection({ width, height }: Props) {
  // Calendar reads from store directly, so just render it
  return (
    <div style={{ width, height, overflow: 'auto' }}>
      <Calendar />
    </div>
  );
}
