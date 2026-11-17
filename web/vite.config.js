import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const api = "http://127.0.0.1:8000";

export default defineConfig({
  base: "/app/",
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { "/api": api, "/docs": api, "/openapi.json": api },
  },
  test: { environment: "jsdom" },
});
