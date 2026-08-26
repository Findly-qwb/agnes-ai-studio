import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5001', changeOrigin: true },
      '/pictures': { target: 'http://127.0.0.1:5001', changeOrigin: true },
      '/videos': { target: 'http://127.0.0.1:5001', changeOrigin: true },
      '/dramas': { target: 'http://127.0.0.1:5001', changeOrigin: true },
      '/anchor': { target: 'http://127.0.0.1:5001', changeOrigin: true },
    },
  },
})