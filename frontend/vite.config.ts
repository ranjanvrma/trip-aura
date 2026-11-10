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
  const google = googleKey ? " https://maps.googleapis.com https://maps.gstatic.com" : "";
  const csp = [
    "default-src 'self'",
    `script-src 'self'${google}`,
    // react-leaflet, motion and the map pins set inline style attributes
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: https://*.tile.openstreetmap.org${google}`,
    "font-src 'self'",
    `connect-src 'self'${api ? " " + api : ""}${google}`,
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
    signin: ["Sign in | TripAura", "Sign in to TripAura with a one-time code sent to your email. No password needed."],
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
  return {
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
