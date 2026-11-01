import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// envDir points at the repo root so the backend and frontend share one `.env`.
// Only variables prefixed with VITE_ are exposed to browser code.
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
