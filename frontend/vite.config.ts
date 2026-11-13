import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Production Content-Security-Policy as a <meta> tag. Response headers (frame-ancestors, HSTS, X-Frame-Options)
 * can't be set from HTML; they belong in the host config (see HANDOFF, Vercel headers).
 */
function contentSecurityPolicy(apiBase: string, googleKey: boolean): Plugin {
  const api = apiBase ? new URL(apiBase).origin : "";
  // Hosts the Maps JavaScript API needs (Google's CSP guide for Maps JS): scripts, tiles, controls and their fonts.
  const g = (list: string) => (googleKey ? " " + list : "");
  const csp = [
    "default-src 'self'",
    `script-src 'self'${g("https://*.googleapis.com https://*.gstatic.com https://*.google.com")}`,
    // react-leaflet, motion and the map pins set inline style attributes
    `style-src 'self' 'unsafe-inline'${g("https://fonts.googleapis.com")}`,
    `img-src 'self' data: blob: https://*.tile.openstreetmap.org${g("https://*.googleapis.com https://*.gstatic.com https://*.google.com https://*.googleusercontent.com")}`,
    `font-src 'self'${g("https://fonts.gstatic.com")}`,
    `connect-src 'self'${api ? " " + api : ""}${g("https://*.googleapis.com https://*.google.com https://*.gstatic.com")}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ].join("; ");
  return {
    name: "tripaura-csp",
    apply: "build",
    transformIndexHtml: (html) => html.replace("<!--CSP-->", `<meta http-equiv="Content-Security-Policy" content="${csp}" />`),
  };
}

/**
 * Pre-renders the <head> of each public route into its own HTML file (dist/terms/index.html, ...), so link previews,
 * crawlers and the first paint get the right title and description before any JavaScript runs.
 */
function prerenderHeads(): Plugin {
  const routes: Record<string, [string, string]> = {
    terms: ["Terms of use | TripAura", "The terms for using TripAura, a free day-by-day trip planner."],
    privacy: ["Privacy policy | TripAura", "What TripAura stores, why, for how long, and who it is shared with."],
    trips: ["My trips | TripAura", "Your saved TripAura itineraries."],
    "404": ["Page not found | TripAura", "This page doesn't exist on TripAura."],
  };
  let outDir = "dist";
  return {
    name: "tripaura-prerender-heads",
    apply: "build",
    configResolved: (c) => { outDir = c.build.outDir; },
    closeBundle() {
      const base = readFileSync(resolve(outDir, "index.html"), "utf8");
      for (const [route, [title, desc]] of Object.entries(routes)) {
        const html = base
          .replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`)
          .replace(/(<meta name="description" content=")[^"]*/, `$1${desc}`)
          .replace(/(<meta property="og:title" content=")[^"]*/, `$1${title}`)
          .replace(/(<meta property="og:description" content=")[^"]*/, `$1${desc}`)
          .replace(/(<meta name="robots" content=")[^"]*/, `$1${route === "trips" || route === "404" ? "noindex" : "index,follow"}`);
        const file = route === "404" ? resolve(outDir, "404.html") : resolve(outDir, route, "index.html");
        mkdirSync(dirname(file), { recursive: true });
        writeFileSync(file, html);
      }
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const { version } = JSON.parse(readFileSync(resolve(process.cwd(), "package.json"), "utf8")) as { version: string };
  return {
    // the release version (package.json), shown in the footer; bump it with every release (see HANDOFF, Versions)
    define: { __APP_VERSION__: JSON.stringify(version) },
    plugins: [react(), contentSecurityPolicy(env.VITE_API_BASE_URL ?? "", !!env.VITE_GOOGLE_MAPS_API_KEY), prerenderHeads()],
    build: {
      chunkSizeWarningLimit: 600,   // three.js (about 130 kB gzipped) loads lazily, only for the globe
      rollupOptions: {
        output: {
          // keep heavy libraries in their own cacheable chunks
          manualChunks: { three: ["three"], motion: ["motion"], gsap: ["gsap"] },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      },
    },
  };
});
