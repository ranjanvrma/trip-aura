import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light";

const KEY = "tripaura.theme";
const EVENT = "tripaura:theme";
// the browser's own chrome (address bar on phones) follows the page background
const CHROME: Record<Theme, string> = { dark: "#0a0f14", light: "#f6f4ef" };

/** The theme on the page right now. `public/theme-init.js` applies the saved choice before the first paint. */
export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/** Switch theme, remember it in this browser, and tell every listener (maps and day colours re-read it). */
export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", CHROME[theme]);
  try { localStorage.setItem(KEY, theme); } catch { /* private mode: the choice lasts for this visit only */ }
  window.dispatchEvent(new Event(EVENT));
}

export const toggleTheme = () => setTheme(getTheme() === "dark" ? "light" : "dark");

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  return () => window.removeEventListener(EVENT, onChange);
}

/** The current theme; the component re-renders when it changes. */
export const useTheme = (): Theme => useSyncExternalStore(subscribe, getTheme);
