import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Person 4 owns this file.  @examples points at shared/examples so fixture mode
// reads the same JSON as every backend test.  @spatial is read-only and lets
// the mode banner show the committed face-basis calibration status.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@examples": path.resolve(__dirname, "../shared/examples"),
      "@spatial": path.resolve(__dirname, "../backend/wattwalk/spatial"),
    },
  },
  server: {
    port: 5173,
    fs: {
      allow: [".."],
    },
  },
});
