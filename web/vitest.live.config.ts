import { defineConfig } from "vitest/config";

// Boots a real Pyodide interpreter. Slow by nature; kept out of the default run.
export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.live.test.ts"],
    testTimeout: 120_000,
    hookTimeout: 120_000,
    fileParallelism: false,
  },
});
