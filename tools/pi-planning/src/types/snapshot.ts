import type {
  WorkItem,
  Person,
  Team,
  PIConfig,
  ProjectConfig,
  GitStatus,
  ObjectivesData,
} from './edpa';

// ─── EDPA snapshot contract ──────────────────────────────────────────────────
// The versioned JSON injected as `window.__EDPA__` by
// `plugin/edpa/scripts/pi_planning.py`. It is the single hand-off between the
// Python generator (the WRITER, which reads `.edpa/`) and this prebuilt React
// bundle (the READER, which renders it strictly read-only).
//
// Why a version: the bundle ships prebuilt inside the plugin, while the Python
// generator runs on every machine and regenerates reports constantly. Stamping
// every snapshot with `schema_version` and having the bundle accept exactly
// `EDPA_SNAPSHOT_SCHEMA` lets those two evolve independently: a report carrying
// an unknown version is refused with a visible "regenerate" message (see
// main.tsx) instead of silently mis-rendering.
//
// Bump `EDPA_SNAPSHOT_SCHEMA` on ANY backward-incompatible change to the shape
// below (removed/renamed/retyped field). Purely additive optional fields do not
// require a bump — old readers ignore them, the generator may omit them.

export const EDPA_SNAPSHOT_SCHEMA = 1;

export interface EdpaSnapshot {
  /** Contract version. Must equal `EDPA_SNAPSHOT_SCHEMA` for this bundle. */
  schema_version: number;
  /** ISO-8601 UTC timestamp the artifact was generated. */
  generated_at: string;
  /** PI the artifact was named/scoped for. All PIs are still present in `pis`. */
  pi?: string;
  project: ProjectConfig;
  people: Person[];
  teams: Team[];
  pis: PIConfig[];
  /** Every backlog item: frontmatter fields + raw markdown `body`, verbatim. */
  backlog: WorkItem[];
  /** PI objectives keyed by PI id (from `.edpa/pi-objectives/<PI>.yaml`). */
  objectives: Record<string, ObjectivesData>;
  /** Git status; a read-only stub in snapshot mode. */
  git: GitStatus;
}

/** True when `s` is a snapshot this bundle can render. */
export function isSupportedSnapshot(s: EdpaSnapshot | undefined): s is EdpaSnapshot {
  return !!s && s.schema_version === EDPA_SNAPSHOT_SCHEMA;
}
