import { useState } from "react";
import { api, ApiError } from "../services/api";
import type { ParsedTrip } from "../types";

const EXAMPLE = "4 days in Lisbon with my partner from 12 Dec, vegetarian, we love museums, street art and sunsets, "
  + "budget 900 euros, staying at Rossio, relaxed pace, metro and walking";

/** Free-text trip description -> form fields (backend NLP parser). */
export default function DescribeTrip({ onParsed }: { onParsed: (p: ParsedTrip) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ParsedTrip | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.parseTrip(text);
      setResult(r);
      onParsed(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read the description");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="describe">
      <h2 className="tile-title">Describe your trip</h2>
      <p className="small muted">Write it the way you'd tell a friend. TripAura fills in the form below; you can then adjust anything.</p>
      <textarea rows={3} maxLength={500} aria-label="Describe your trip" value={text} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim().length > 2) void run(); }} />
      <div className="row gap-s wrap mt-s">
        <button type="button" className="btn" onClick={() => void run()} disabled={busy || text.trim().length < 3}>
          {busy ? <><span className="spinner" aria-hidden /> Reading</> : "Fill the form"}
        </button>
        <span className="small muted shortcut-hint"><kbd className="kbd">Ctrl</kbd><kbd className="kbd">Enter</kbd></span>
        <button type="button" className="btn" onClick={() => setText(EXAMPLE)}>Use example</button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      {result && (
        <div className="mt-s">
          {result.understood.length > 0 && (
            <div className="chips">{result.understood.map((u) => <span key={u} className="chip chip-on" role="status">{u}</span>)}</div>
          )}
          {result.notes.map((n) => <p key={n} className="small warn">{n}</p>)}
        </div>
      )}
    </section>
  );
}
