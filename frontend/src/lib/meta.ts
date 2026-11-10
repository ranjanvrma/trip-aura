import { useEffect } from "react";

const SITE = "TripAura";
const DEFAULT_DESCRIPTION =
  "Plan a day-by-day trip for any city: sights in a sensible order, meals that fit your diet, transport and a budget, built from open map data.";

function setMeta(selector: string, attr: string, value: string) {
  let el = document.head.querySelector<HTMLMetaElement | HTMLLinkElement>(selector);
  if (!el) {
    const [tag, rest] = selector.split("[");
    el = document.createElement(tag) as HTMLMetaElement;
    const m = /([\w:-]+)="([^"]+)"/.exec(rest ?? "");
    if (m) el.setAttribute(m[1], m[2]);
    document.head.appendChild(el);
  }
  el.setAttribute(attr, value);
}

/** Page title, description, canonical URL and Open Graph tags. Uses the current origin, so any custom domain works. */
export function usePageMeta(title: string | null, description = DEFAULT_DESCRIPTION, { noindex = false } = {}) {
  useEffect(() => {
    const full = title ? `${title} | ${SITE}` : `${SITE} | Day-by-day trip planner`;
    document.title = full;
    const url = window.location.origin + window.location.pathname;
    setMeta('meta[name="description"]', "content", description);
    setMeta('meta[property="og:title"]', "content", full);
    setMeta('meta[property="og:description"]', "content", description);
    setMeta('meta[property="og:url"]', "content", url);
    setMeta('link[rel="canonical"]', "href", url);
    setMeta('meta[name="robots"]', "content", noindex ? "noindex" : "index,follow");
  }, [title, description, noindex]);
}
