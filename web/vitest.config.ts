import { defineConfig } from "vitest/config";

// Two projects. The default one is pure TypeScript and runs in milliseconds.
// `live` boots a real Pyodide interpreter per file (~1.5 s) to check the live
// source against Python, so it is opt-in: `npm run test:live`.
export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["src/**/*.live.test.ts"],
    testTimeout: 20_000,
  },
});
