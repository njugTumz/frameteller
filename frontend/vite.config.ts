/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

/** STUDIO_NOINDEX=1 (staging) puts a robots noindex tag in index.html, so no page of that site is ever indexed. */
const noindex: Plugin = {
  name: 'studio-noindex',
  transformIndexHtml: (html) =>
    process.env.STUDIO_NOINDEX === '1' ? html.replace('</title>', '</title>\n    <meta name="robots" content="noindex, nofollow" />') : html,
}

export default defineConfig({
  plugins: [react(), tailwindcss(), noindex],
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
    restoreMocks: true,
  },
})
