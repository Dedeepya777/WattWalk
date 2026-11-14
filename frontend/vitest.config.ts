import { defineConfig } from "vitest/config";

// sdkFrame.ts is pure, so the unit tests run in plain Node without a DOM.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
