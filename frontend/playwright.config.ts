import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e", timeout: 60_000,
  use: { baseURL: "http://localhost:5173", launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] } },
  webServer: [
    { command: "cd ../backend && AI_MODE=demo STORAGE_BACKEND=memory APP_SECRET=0123456789abcdef0123456789abcdef0123 python -m uvicorn app.main:app --port 8000", url: "http://localhost:8000/api/health/live", reuseExistingServer: true },
    { command: "VITE_API_URL=http://localhost:8000 npm run dev -- --port 5173", url: "http://localhost:5173", reuseExistingServer: true },
  ],
});
