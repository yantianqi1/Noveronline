import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "0.0.0.0",
    port: 3999,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:3888",
        changeOrigin: true,
      },
    },
  },
});
