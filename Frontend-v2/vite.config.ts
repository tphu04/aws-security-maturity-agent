import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5174,
    proxy: {
      "/api/chatbot": {
        target: "http://127.0.0.1:9002",
        rewrite: (p) => p.replace(/^\/api\/chatbot/, ""),
        changeOrigin: true,
      },
      "/api/scanner": {
        target: "http://127.0.0.1:9001",
        rewrite: (p) => p.replace(/^\/api\/scanner/, ""),
        changeOrigin: true,
      },
      "/api/rag": {
        target: "http://127.0.0.1:9005",
        rewrite: (p) => p.replace(/^\/api\/rag/, ""),
        changeOrigin: true,
      },
    },
  },
});
