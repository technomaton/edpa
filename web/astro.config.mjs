import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  // Production origin — required for absolute canonical URLs, hreflang
  // alternates (src/layouts/Layout.astro) and @astrojs/sitemap.
  site: 'https://edpa.technomaton.com',
  integrations: [
    sitemap({
      // Client-specific kashealth decks/dashboards stay reachable but are
      // not advertised in the public sitemap.
      filter: (page) => !page.includes('/kashealth/'),
    }),
  ],
});
