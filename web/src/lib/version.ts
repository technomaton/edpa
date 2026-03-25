// Single source of truth: reads from plugin.json at build time
// All components import { VERSION } from this file
import pluginData from '../../../.claude/.claude-plugin/plugin.json';
export const VERSION = pluginData.version;
