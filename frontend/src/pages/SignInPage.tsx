import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";
import { safeNext, useAuth } from "../lib/auth";
import { usePageMeta } from "../lib/meta";
import { clearCache } from "../lib/swr";
import { useToast } from "../lib/toast";
import { api, ApiError } from "../services/api";
import type { ApiStatus } from "../types";

const RESEND_AFTER_S = 30;

export default function SignInPage({ status }: { status: ApiStatus | null }) {
  usePageMeta("Sign in", "Sign in to TripAura with a one-time code sent to your email. No password needed.");
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const nav = useNavigate();
  const toast = useToast();
  const { user, signedIn } = useAuth();

  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const codeInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => window.clearTimeout(t);
  }, [cooldown]);
  useEffect(() => { if (step === "code") codeInput.current?.focus(); }, [step]);

  if (user && step === "email") return <Navigate to={next} replace />;

  const send = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.requestCode(email.trim());
      setStep("code");
      setCode("");
      setCooldown(RESEND_AFTER_S);
      toast.show({ tone: "success", message: `Code sent to ${email.trim()}` });
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (value = code) => {
    if (!/^\d{6}$/.test(value) || busy) return;
    setBusy(true);
    setError(null);
    try {
      const s = await api.verifyCode(email.trim(), value);
      clearCache();
      signedIn(s);
      toast.show({ tone: "success", message: "You're signed in" });
      nav(next, { replace: true, viewTransition: true });
    } catch (err) {
      const e = err as ApiError;
      setError(e.code === "invalid_code" ? "That code didn't work. Check the latest email, or send a new code." : e.message);
      setCode("");
      codeInput.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const devCodes = status?.auth?.dev_codes_in_console;

  return (
    <div className="narrow">
      <section className="tile auth" aria-labelledby="signin-title">
        <span className="auth-icon" aria-hidden><Mail size={20} /></span>
        <h1 id="signin-title" className="h2">{step === "email" ? "Sign in to TripAura" : "Check your email"}</h1>

        {step === "email" ? (
          <form onSubmit={(e) => void send(e)} className="stack-m" noValidate={false}>
            <p className="muted">We'll email you a 6-digit code. There's no password to remember, and a new account is created the first time.</p>
            <label className="field">
              <span>Email address</span>
              <input type="email" inputMode="email" autoComplete="email" required maxLength={254} autoFocus
                     value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"
                     aria-invalid={!!error} aria-describedby={error ? "signin-error" : undefined} />
            </label>
            {error && <p id="signin-error" className="field-error" role="alert">{error}</p>}
            <button className="btn btn-primary btn-block" disabled={busy || !email.includes("@")}>
              {busy ? <><span className="spinner" aria-hidden /> Sending</> : "Email me a code"}
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void verify(); }} className="stack-m">
            <p className="muted">Enter the code we sent to <strong>{email}</strong>. It expires in 10 minutes.</p>
            <label className="field">
              <span>6-digit code</span>
              <input ref={codeInput} className="otp" type="text" inputMode="numeric" autoComplete="one-time-code"
                     pattern="\d{6}" maxLength={6} required value={code}
                     aria-invalid={!!error} aria-describedby={error ? "code-error" : undefined}
                     onChange={(e) => {
                       const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                       setCode(v);
                       if (v.length === 6) void verify(v);   // pasted or autofilled codes submit themselves
                     }} />
            </label>
            {error && <p id="code-error" className="field-error" role="alert">{error}</p>}
            {devCodes && <p className="notice notice-info small">Development mode: the code is printed in the backend console.</p>}
            <button className="btn btn-primary btn-block" disabled={busy || code.length !== 6}>
              {busy ? <><span className="spinner" aria-hidden /> Checking</> : "Sign in"}
            </button>
            <div className="row between wrap gap-s small">
              <button type="button" className="link" onClick={() => { setStep("email"); setError(null); }}>
                <ArrowLeft size={14} aria-hidden /> Use a different email
              </button>
              <button type="button" className="link" disabled={cooldown > 0 || busy} onClick={() => void send()}>
                {cooldown > 0 ? <span className="num">Send a new code in {cooldown}s</span> : "Send a new code"}
              </button>
            </div>
          </form>
        )}
        <p className="small muted auth-legal">
          By signing in you agree to the <Link to="/terms">Terms of use</Link> and the <Link to="/privacy">Privacy policy</Link>.
        </p>
      </section>
    </div>
  );
}
