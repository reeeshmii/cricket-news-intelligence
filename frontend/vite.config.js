import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs separately (python -m src.api); Vite forwards /api to it.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom", "react-router-dom"] } },
    },
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
