import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_BACKEND_TARGET
  || process.env.KAOYAN_BACKEND_URL
  || `http://127.0.0.1:${process.env.KAOYAN_BACKEND_PORT || '8000'}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), {
    name: 'texa-startup-build-id',
    transformIndexHtml(html) {
      return html.replace('__TEXA_BUILD_ID__', new Date().toISOString());
    },
  }],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    // Keep hashed modules referenced by phones already using the previous shell.
    emptyOutDir: false,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            // Capture React first so feature chunks cannot absorb its runtime.
            { name: 'vendor-react', test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/, priority: 30 },
            { name: 'vendor-icons', test: /node_modules[\\/]lucide-react[\\/]/, priority: 20 },
          ],
        },
      },
    },
  },
})
