import { cleanup } from "@testing-library/react";
import { afterEach } from "vite-plus/test";

// Testing Library unmounts after each test only through a global `afterEach`,
// which Vitest does not provide without `globals`; so it is wired here.
afterEach(() => {
  cleanup();
});
