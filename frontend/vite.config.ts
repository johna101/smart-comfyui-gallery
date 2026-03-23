import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    // Proxy all /galleryout/* requests to the Flask backend
    proxy: {
      '/galleryout': {
        target: 'http://127.0.0.1:8189',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Output to Flask's static directory for production
    outDir: '../static/dist',
    emptyOutDir: true,
  },
})
