import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  return {
    plugins: [
      react(), 
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.ico', 'apple-touch-icon.png', 'mask-icon.svg'],
        manifest: {
          name: 'Nexus Response Unit',
          short_name: 'Nexus',
          description: 'Emergency Operations Center for Humanitarian Relief',
          theme_color: '#312e81',
          icons: [
            {
              src: 'pwa-192x192.png',
              sizes: '192x192',
              type: 'image/png'
            },
            {
              src: 'pwa-512x512.png',
              sizes: '512x512',
              type: 'image/png'
            }
          ]
        },
        devOptions: {
          enabled: false
        }
      })
    ],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      hmr: process.env.DISABLE_HMR !== 'true',
      proxy: {
        '/api/registry': {
          target: 'http://localhost:8001',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/registry/, ''),
        },
        '/api/ingestion': {
          target: 'http://localhost:8002',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/ingestion/, ''),
        },
        '/api/coordination': {
          target: 'http://localhost:8003',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/coordination/, ''),
        },
        '/proxy': {
          target: 'http://localhost:3001',
          changeOrigin: true,
        },
        '/api/proxy': {
          target: 'http://localhost:3001',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/proxy/, '/proxy'),
        },
        '/api/intelligence': {
          target: 'http://localhost:8004',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/intelligence/, ''),
        },
        '/api/analytics': {
          target: 'http://localhost:8005',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/analytics/, ''),
        },
      },
    },
  };
});
