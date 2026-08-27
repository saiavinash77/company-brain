import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// Two pages, both with absolute asset URLs (base '/floor/'):
//   index.html  -> chat landing (/)  + "Open Office Floor" button
//   floor.html  -> standalone floor page (/floor)
// Agno's middleware strips trailing slashes, which breaks relative
// "./assets" resolution, so we keep base absolute.

export default defineConfig({
  base: '/floor/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        floor: resolve(__dirname, 'floor.html'),
      },
    },
    chunkSizeWarningLimit: 1600,
  },
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/teams': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
