import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Las llamadas a /api se redirigen al backend FastAPI en desarrollo.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
