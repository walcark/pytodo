import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build straight into the Python package so the wheel ships the compiled SPA
// and the runtime needs no node. FastAPI serves this directory (see app.py).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL('../src/neverland/server/static', import.meta.url)),
    emptyOutDir: true,
  },
})
