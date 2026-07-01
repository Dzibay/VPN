import path from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Отдельный frontend для admin.<domain>.
 * - Свой staff-JWT (login на POST /api/staff/auth/login), заголовок X-Admin-Project.
 * - Собирается независимо, деплой — nginx-admin (см. docker-compose).
 * - Часть view-компонентов переиспользуется из ../frontend/src/views/* через alias @legacy-views.
 */
const API_TARGET = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      // Переиспользование существующих admin-view до момента их окончательного переноса.
      '@legacy-views': path.resolve(__dirname, '../frontend/src/views'),
      '@legacy-components': path.resolve(__dirname, '../frontend/src/components'),
      '@legacy-composables': path.resolve(__dirname, '../frontend/src/composables'),
      '@legacy-utils': path.resolve(__dirname, '../frontend/src/utils'),
      '@legacy-api': path.resolve(__dirname, '../frontend/src/api'),
    },
  },
  build: {
    chunkSizeWarningLimit: 300,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('node_modules/chart.js/')) return 'chart-vendor'
          if (
            id.includes('node_modules/vue-router/') ||
            /node_modules\/@vue\//.test(id) ||
            /node_modules\/vue\//.test(id)
          ) {
            return 'vue-vendor'
          }
        },
      },
    },
  },
  server: {
    host: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      '/swagger': { target: API_TARGET, changeOrigin: true },
    },
  },
})
