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
    coverage: { reporter: ['text', 'html'] },
  },
});
