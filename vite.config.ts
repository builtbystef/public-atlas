import { defineConfig } from "vite-plus";

export default defineConfig({
  staged: {
    "*": "vp check --fix",
    "*.py": ["uv run ruff check --fix", "uv run ruff format"],
  },
  // Vendored agent tooling. Excluded here, not only via .gitignore, so it never
  // fails checks if it is committed.
  fmt: {
    ignorePatterns: [
      "**/.agents/**",
      "**/.claude/**",
      "**/.next/**",
      "**/src/generated/**",
      "packages/api-client/openapi.json",
      // Prose, kept as written.
      "docs/**",
    ],
  },
  lint: {
    options: {
      typeAware: true,
      typeCheck: true,
    },
    rules: {
      "no-duplicate-imports": "error",
    },
    ignorePatterns: [
      "**/dist/**",
      "**/.next/**",
      "**/coverage/**",
      "**/.agents/**",
      "**/.claude/**",
      "**/src/generated/**",
    ],
    overrides: [
      {
        files: ["**/*.test.ts", "**/*.spec.ts"],
        plugins: ["vitest"],
      },
    ],
  },
  test: {
    passWithNoTests: true,
    // Each package is its own project, so `apps/web/vite.config.ts` (the `@/`
    // alias) applies to its tests when run from the root too.
    projects: ["apps/web", "packages/api-client"],
  },
  pack: {
    dts: true,
    sourcemap: true,
  },
  run: {
    cache: true,
    tasks: {
      // A task, not a script, so it can opt out of caching for good: the runner traces a
      // cached command's file reads with a preloaded library, which Chromium's sandboxed
      // renderers crash on, and the browser tests then find their tab closed. The suite
      // reads a database and starts a browser, so a cache would not be right anyway.
      "test:py": { command: "uv run pytest", cache: false },
    },
  },
});
