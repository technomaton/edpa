// EDPA version — single source of truth is the plugin manifest
// (plugin/.claude-plugin/plugin.json). The web ships as a slice of the
// same monorepo release as the engine, so site copy mirrors the
// engine version that matches the current git tag and CHANGELOG entry.
//
// Bumping: when the plugin version changes, also bump web/package.json
// to the same value so Vercel's deployment metadata stays aligned.
import pluginManifest from '../../../plugin/.claude-plugin/plugin.json';
export const VERSION: string = pluginManifest.version;
