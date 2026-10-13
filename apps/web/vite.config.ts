import { fileURLToPath } from "node:url";

import { defineConfig } from "vite-plus";

/** Tests resolve `@/` the way tsconfig does; Next handles it for the app itself. */
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  // tsconfig says `jsx: preserve` for Next; a .tsx test needs the JSX compiled.
  oxc: { jsx: { runtime: "automatic" } },
  test: {
    // A test that renders says so with `// @vitest-environment jsdom`; the rest run in Node.
    setupFiles: ["./src/test/setup.ts"],
    // The Playwright smoke (e2e/) drives the built console; `vp run test:e2e` runs it.
    exclude: ["**/node_modules/**", "e2e/**"],
  },
});
