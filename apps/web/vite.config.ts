import { fileURLToPath } from "node:url";

import { defineConfig } from "vite-plus";

/** Tests resolve `@/` the way tsconfig does; Next handles it for the app itself. */
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
});
