import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

function buildHash(): string {
  // A Docker build has no .git: take BUILD_HASH, or the commit a host passes as a build arg.
  const given = process.env.BUILD_HASH || process.env.RENDER_GIT_COMMIT || process.env.RAILWAY_GIT_COMMIT_SHA;
  if (given) return given.slice(0, 7);
  try {
    return execSync("git rev-parse --short HEAD", { cwd: repoRoot }).toString().trim();
  } catch {
    return "unknown";
  }
}

// The FastAPI server: uv run uvicorn app.main:app --app-dir server --port 8000
const apiProxy = { "/api": { target: "http://127.0.0.1:8000" } };

export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_HASH__: JSON.stringify(buildHash()),
    __BUILD_DATE__: JSON.stringify(new Date().toISOString().slice(0, 10)),
  },
  server: { port: 5173, fs: { allow: [repoRoot] }, proxy: apiProxy },
  preview: { port: 4173, proxy: apiProxy },
  test: { include: ["src/**/*.test.ts"] },
});
