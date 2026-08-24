import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' so the built page works when FastAPI serves it under /floor
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1600,
  },
})
