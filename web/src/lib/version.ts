// EDPA version — reads from web/package.json (single source of truth).
// Surfacing the live build version in product copy makes it visible
// that the project is actively maintained and ties what the reader
// sees on the site to a specific commit / changelog entry.
import pkg from '../../package.json';
export const VERSION = pkg.version;
