import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
const adapter = fileURLToPath(new URL("./src/api.js", import.meta.url));
export default defineConfig({
  plugins: [
    {
      name: "nora-provider-boundary",
      enforce: "pre",
      resolveId(source, importer) {
        if (
          importer &&
          importer.includes("/packages/studio/src/") &&
          /^(\.\.\/|\.\/)muapi(?:\.js)?$/.test(source)
        )
          return adapter;
        if (
          importer &&
          importer.includes("/packages/studio/src/") &&
          /^(\.\.\/|\.\/)models(?:\.js)?$/.test(source)
        )
          return fileURLToPath(new URL("./src/models.js", import.meta.url));
      },
    },
    react(),
  ],
  base: process.env.NORA_BASE || "/",
  server: {
    host: "127.0.0.1",
    port: 38789,
    fs: { allow: [".."] },
    proxy: {
      "/api": "http://127.0.0.1:36440",
      "/media": "http://127.0.0.1:36440",
    },
  },
  resolve: {
    alias: {
      "@nora/runtime": fileURLToPath(
        new URL("./src/runtime.js", import.meta.url),
      ),
      "@nora/ui": fileURLToPath(new URL("./src/ui.jsx", import.meta.url)),
    },
    dedupe: [
      "react",
      "react-dom",
      "react-hot-toast",
      "axios",
      "react-icons",
      "lucide-react",
    ],
  },
  build: { outDir: "dist", emptyOutDir: true },
});
