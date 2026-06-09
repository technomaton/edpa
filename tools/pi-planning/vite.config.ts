import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

// `build` → one self-contained index.html (JS + CSS inlined, no external
// requests) that `pi_planning.py` hydrates with project data. `serve` (dev)
// keeps the /api proxy to the Express backend for live editing.
export default defineConfig(({ command }) => ({
  plugins: [
    react(),
    tailwindcss(),
    ...(command === 'build' ? [viteSingleFile()] : []),
  ],
  // Inline ALL assets (the self-hosted woff2 fonts) as base64 so the built
  // single file makes zero external requests. viteSingleFile then folds the
  // CSS (with the data: font URLs) into the HTML.
  build: {
    assetsInlineLimit: 100_000_000,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:3001',
    },
  },
}));
