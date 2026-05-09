// EDPA methodology version — semantic, surfaced in product copy.
//
// Bump rules:
//   1.0 → 1.1   non-breaking methodology refinement (e.g. extra signal type)
//   1.x → 2.0   breaking change in the model (formula, invariants, schema)
//
// The web build version lives in web/package.json (e.g. 1.6.4-beta) and
// is used for cache busting / deploy tracking — not surfaced to readers.
//
// 1.0 = additive signal aggregation + per-item CW normalization + gated
//       calculation (Story Done + Feature/Epic/Initiative gate transitions).
//       Stable since the v1.11 plugin refactor.
export const VERSION = '1.0';
