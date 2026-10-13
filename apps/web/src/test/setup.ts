import { cleanup } from "@testing-library/react";
import { afterEach } from "vite-plus/test";

// Testing Library's automatic cleanup needs a global `afterEach`, which Vitest lacks
// without `globals`.
afterEach(() => {
  cleanup();
});
