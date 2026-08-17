import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.GITHUB_ACTIONS ? "/a-share-signal-lab/" : "/",
  plugins: [react()],
  test: { environment: "jsdom", setupFiles: "./tests/setup.ts" },
});
