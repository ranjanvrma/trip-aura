import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from "../services/api";
import type { AuthSession, AuthUser } from "../types";

interface AuthState {
  user: AuthUser | null;
  checking: boolean;
  /** Called after a successful code check. */
  signedIn: (s: AuthSession) => void;
  signOut: () => Promise<void>;
  /** Permanently deletes the account, its trips and sessions. */
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);

  const signedIn = useCallback((s: AuthSession) => {
    setCsrfToken(s.csrf_token);
    setUser(s.user);
  }, []);

  const clear = useCallback(() => { setCsrfToken(null); setUser(null); }, []);

  useEffect(() => {
    let cancelled = false;
    api.me()
      .then((s) => { if (!cancelled) signedIn(s); })
      .catch((e: ApiError) => { if (!cancelled && e.status === 401) clear(); })
      .finally(() => { if (!cancelled) setChecking(false); });
    setUnauthorizedHandler(clear);   // session expired mid-use
    return () => { cancelled = true; setUnauthorizedHandler(null); };
  }, [signedIn, clear]);

  const signOut = useCallback(async () => {
    try { await api.logout(); } finally { clear(); }
  }, [clear]);

  const deleteAccount = useCallback(async () => {
    await api.deleteAccount();
    clear();
  }, [clear]);

  const value = useMemo(() => ({ user, checking, signedIn, signOut, deleteAccount }),
    [user, checking, signedIn, signOut, deleteAccount]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Only same-site paths are allowed as a post-sign-in destination (blocks open redirects such as //evil.com or /\evil.com). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/";
  return next;
}
