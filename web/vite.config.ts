import { defineConfig } from 'vitest/config';
import { VitePWA } from 'vite-plugin-pwa';

// Les couleurs du manifeste reprennent les jetons --color-navy et --color-ivory
// de src/styles.css : un manifeste JSON ne lit pas les variables CSS.
export default defineConfig({
  plugins: [
    VitePWA({
      registerType: 'autoUpdate',
      // L'enregistrement est fait par src/main.tsx, qui en attrape le refus.
      injectRegister: null,
      workbox: {
        // Une navigation vers l'API n'est jamais servie par l'index mis en cache.
        navigateFallbackDenylist: [/^\/api/],
      },
      manifest: {
        name: 'Graffard Racing',
        short_name: 'Graffard',
        lang: 'fr',
        start_url: '/',
        display: 'standalone',
        theme_color: '#142E3B',
        background_color: '#F5F2EB',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:3000',
    },
  },
  test: {
    environment: 'node',
  },
});
