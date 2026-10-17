import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // the family dashboard chunk (AG Grid) is big but loads only on /dashboard
  build: { chunkSizeWarningLimit: 1500 },
});
