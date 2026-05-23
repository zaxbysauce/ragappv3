/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// VITE_APP_BASENAME: Build-time path prefix for asset URLs. Application code reads this via import.meta.env.VITE_APP_BASENAME at runtime.
export const appBasename = process.env.VITE_APP_BASENAME || ''
const normalizedBasename = appBasename.replace(/\/+$/, '')

export default defineConfig({
  base: normalizedBasename || '/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-ui': ['framer-motion', '@radix-ui/react-dialog', '@radix-ui/react-select', '@radix-ui/react-tabs'],
          'vendor-state': ['zustand', '@tanstack/react-query', 'axios'],
        },
      },
    },
  },
  server: {
    port: 3000,
    host: true,
    proxy: {
      [normalizedBasename ? `${normalizedBasename}/api` : '/api']: {
        target: 'http://localhost:9090',
        changeOrigin: true,
        rewrite: normalizedBasename
          ? (path) => path.replace(new RegExp(`^${normalizedBasename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`), '')
          : undefined,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globalSetup: ['./src/test/global-setup.ts'],
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
  },
})
