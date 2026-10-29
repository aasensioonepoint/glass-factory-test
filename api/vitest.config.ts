import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    // PGlite boots a WASM Postgres per case: 1.3-1.8 s at rest, more under EDR load.
    testTimeout: 30000,
  },
});
