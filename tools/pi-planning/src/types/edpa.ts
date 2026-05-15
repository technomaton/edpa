export interface Contributor {
  person: string;
  role: string;
  cw: number;
  rs?: number;
}

export type ItemType = 'Initiative' | 'Epic' | 'Feature' | 'Story' | 'Defect' | 'Event' | 'Risk';
export type PortfolioStatus = 'Funnel' | 'Reviewing' | 'Analyzing' | 'Ready' | 'Implementing' | 'Done';
export type DeliveryStatus = 'Funnel' | 'Analyzing' | 'Backlog' | 'Implementing' | 'Validating' | 'Deploying' | 'Releasing' | 'Done';
export type ItemStatus = PortfolioStatus | DeliveryStatus | 'Planned' | 'In Progress' | 'Active';

export const PORTFOLIO_STATUSES: PortfolioStatus[] = ['Funnel', 'Reviewing', 'Analyzing', 'Ready', 'Implementing', 'Done'];
export const DELIVERY_STATUSES: DeliveryStatus[] = ['Funnel', 'Analyzing', 'Backlog', 'Implementing', 'Validating', 'Deploying', 'Releasing', 'Done'];

export interface KanbanColumnConfig {
  status: string;
  label: string;
  wipLimit?: number;
  subColumns?: { key: string; label: string }[];
}
export type RoamStatus = 'resolved' | 'owned' | 'accepted' | 'mitigated';
export type Severity = 'low' | 'medium' | 'high';

export interface WorkItem {
  id: string;
  type: ItemType;
  title: string;
  js: number;
  bv?: number;
  tc?: number;
  rr?: number;
  wsjf?: number;
  status: ItemStatus;
  parent: string | null;
  iteration?: string;
  assignee?: string;
  owner?: string;
  contributors: Contributor[];
  iteration_half?: 1 | 2;
  depends_on?: string[];
  epic_type?: 'Business' | 'Enabler';
  implementing_phase?: 'MVP' | 'Persevere';
  roam_status?: RoamStatus;
  severity?: Severity;
  description?: string;
  /** Raw Markdown body — source of truth for prose (description / AC / notes). */
  body?: string;
}

export interface Person {
  id: string;
  name: string;
  role: string;
  team: string;
  fte: number;
  capacity: number;
}

export interface Team {
  id: string;
  planning_factor: number;
  type?: 'internal' | 'external' | 'shared_service';
}

export interface Iteration {
  id: string;
  dates: string;
  status: 'planned' | 'active' | 'closed';
  type?: string;
}

export interface PIEvent {
  type: 'pi_planning' | 'system_demo' | 'inspect_adapt' | 'prioritization' | 'custom';
  title: string;
  date: string;
  duration?: string;
  iteration?: string;
}

export interface PIConfig {
  id: string;
  status: 'active' | 'planning' | 'closed';
  pi_iterations: number;
  iteration_weeks: number;
  iterations: Iteration[];
  shared_services?: string[];
  events?: PIEvent[];
}

export interface ProjectConfig {
  name: string;
  registration?: string;
  organization?: string;
}

export interface GitStatus {
  branch: string;
  dirty: string[];
  ahead: number;
}

export type ObjStatus = 'done' | 'in_progress' | 'planned';

export interface PIObjective {
  title: string;
  bv: number;
  status: ObjStatus;
}

export interface TeamObjectives {
  committed: PIObjective[];
  stretch: PIObjective[];
  confidence: number;
}

export interface ObjectivesData {
  pi: string;
  teams: Record<string, TeamObjectives>;
}
