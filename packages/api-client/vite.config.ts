import { defineConfig } from "vite-plus";

export default defineConfig({
  run: {
    // Both tasks run apps/server's Python to export the schema, which the task
    // cache cannot fingerprint, so never cache them.
    tasks: {
      generate: { command: "node scripts/generate.ts", cache: false },
      "generate:check": { command: "node scripts/generate.ts --check", cache: false },
    },
  },
});
