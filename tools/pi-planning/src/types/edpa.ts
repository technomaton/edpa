export interface Contributor {
  person: string;
  role: string;
  cw: number;
  rs?: number;
}

export type ItemType = 'Initiative' | 'Epic' | 'Feature' | 'Story' | 'Defect' | 'Milestone' | 'Event';
export type ItemStatus = 'Planned' | 'In Progress' | 'Active' | 'Done';

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

export interface PIConfig {
  id: string;
  status: 'active' | 'planning' | 'closed';
  pi_iterations: number;
  iteration_weeks: number;
  iterations: Iteration[];
  shared_services?: string[];  // team IDs of external/shared service teams for this PI
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
