import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 4173 },
  preview: { port: 4173 },
  test: {
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    css: true,
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
    // The clients read their base URLs from configuration, so the suite supplies test
    // values rather than letting an unset URL change the code path under test.
    env: {
      VITE_ESB_API_URL: 'http://esb.test',
    },
    coverage: { reporter: ['text', 'html'] },
  },
});
