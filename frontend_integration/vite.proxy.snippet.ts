// vite.config.ts - add the `server.proxy` block. With it you can leave VITE_API_BASE_URL empty and CORS never matters during development.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
});
