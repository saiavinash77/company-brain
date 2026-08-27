import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base '/floor/' -> absolute asset URLs, correct no matter whether the page
// is served at "/" or "/floor" (agno's middleware strips trailing slashes,
// which breaks relative "./assets" resolution).
export default defineConfig({
  base: '/floor/',
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
