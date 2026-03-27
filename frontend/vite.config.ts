import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Proxy OTLP HTTP to Jaeger so the browser can POST traces same-origin (no CORS).
    proxy: {
      "/otel": {
        target: "http://localhost:4318",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/otel/, ""),
      },
    },
  },
})
