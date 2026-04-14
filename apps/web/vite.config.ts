import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiHost = process.env.MRN_WEB_API_HOST || "127.0.0.1";
const apiPort = process.env.MRN_WEB_API_PORT || "9090";
const apiTarget = process.env.MRN_WEB_API_TARGET || `http://${apiHost}:${apiPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 9000,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
