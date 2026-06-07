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
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:3001',
    },
  },
}));
