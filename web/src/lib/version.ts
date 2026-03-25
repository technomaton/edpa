// EDPA version — reads from package.json (single source of truth)
// To bump: edit web/package.json "version" field → rebuild
import pkg from '../../package.json';
export const VERSION = pkg.version;
