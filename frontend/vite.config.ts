/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'

const pkg = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf-8'),
) as { version: string }

// Expose the build identity to the SPA. Set on process.env rather than via
// `define`, because `define` is only substituted in the production build — in
// dev the raw token reaches the browser and throws a ReferenceError. Vite picks
// up VITE_-prefixed process.env vars for import.meta.env in both modes.
process.env.VITE_APP_VERSION = pkg.version
process.env.VITE_BUILD_TIME = new Date().toISOString()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        // 8000 collides with the los_backend Docker container on this machine;
        // Compliance's local dev backend runs on 8010 instead.
        target: 'http://localhost:8010',
        changeOrigin: true,
      }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
  },
})
