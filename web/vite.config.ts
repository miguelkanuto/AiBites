import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento, /api vai para a API Python (uvicorn na porta 8001).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8001", changeOrigin: false } },
  },
});
