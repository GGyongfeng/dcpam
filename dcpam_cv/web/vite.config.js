import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    fs: {
      allow: ["../../"],
    },
    host: "127.0.0.1",
    port: 5173,
  },
});
