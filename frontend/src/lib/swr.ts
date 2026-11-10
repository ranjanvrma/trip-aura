import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

/**
 * Minimal stale-while-revalidate cache: cached data is returned at once, then refreshed in the background
 * (on mount, when the tab regains focus, and on demand). Entries can be updated optimistically with `mutate`.
 */
interface Entry<T> { data?: T; error?: Error; at: number; promise?: Promise<T> }
const cache = new Map<string, Entry<unknown>>();
const listeners = new Map<string, Set<() => void>>();

function emit(key: string) { listeners.get(key)?.forEach((fn) => fn()); }
function subscribe(key: string, fn: () => void) {
  if (!listeners.has(key)) listeners.set(key, new Set());
  listeners.get(key)!.add(fn);
  return () => { listeners.get(key)?.delete(fn); };
}

export function mutate<T>(key: string, update: T | ((old: T | undefined) => T)) {
  const e = (cache.get(key) ?? { at: 0 }) as Entry<T>;
  const data = typeof update === "function" ? (update as (o: T | undefined) => T)(e.data) : update;
  cache.set(key, { ...e, data, error: undefined, at: Date.now() });
  emit(key);
}

/** Fill an empty entry without notifying anyone; safe to call during render. */
export function seed<T>(key: string, data: T) {
  if (!cache.get(key)?.data) cache.set(key, { data, at: Date.now() });
}

export function invalidate(key: string) {
  const e = cache.get(key);
  if (e) { cache.set(key, { ...e, at: 0 }); emit(key); }
}

export function clearCache() { cache.clear(); listeners.forEach((_, k) => emit(k)); }

async function revalidate<T>(key: string, fetcher: () => Promise<T>): Promise<void> {
  const e = (cache.get(key) ?? { at: 0 }) as Entry<T>;
  if (e.promise) return void (await e.promise.catch(() => undefined));
  const promise = fetcher();
  cache.set(key, { ...e, promise });
  emit(key);
  try {
    const data = await promise;
    cache.set(key, { data, at: Date.now() });
  } catch (error) {
    cache.set(key, { ...e, error: error as Error, at: Date.now(), promise: undefined });
  }
  emit(key);
}

export function useSWR<T>(key: string | null, fetcher: () => Promise<T>, { dedupeMs = 2000 } = {}) {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const snapshot = useSyncExternalStore(
    useCallback((fn) => (key ? subscribe(key, fn) : () => undefined), [key]),
    () => (key ? cache.get(key) : undefined) as Entry<T> | undefined,
  );

  const refresh = useCallback(() => (key ? revalidate(key, () => fetcherRef.current()) : Promise.resolve()), [key]);

  useEffect(() => {
    if (!key) return;
    const e = cache.get(key);
    if (!e || Date.now() - e.at > dedupeMs) void refresh();
    const onFocus = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", onFocus);
    return () => document.removeEventListener("visibilitychange", onFocus);
  }, [key, refresh, dedupeMs]);

  return {
    data: snapshot?.data,
    error: snapshot?.error,
    loading: !!key && snapshot?.data === undefined && !snapshot?.error,
    refresh,
  };
}
