import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Прокси на API: порт должен совпадать с локальным uvicorn (по умолчанию 5000).
const API_TARGET = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:5000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/sub': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/swagger': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/redoc': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/openapi.json': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
