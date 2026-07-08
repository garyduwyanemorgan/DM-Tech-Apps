import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

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
  }
})
