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
    <section className="card describe">
      <h3>Describe your trip</h3>
      <p className="small muted">Write it the way you'd tell a friend. TripAura fills in the form below; you can then adjust anything.</p>
      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim().length > 2) void run(); }} />
      <div className="row gap-s wrap mt-s">
        <button type="button" className="btn btn-light" onClick={() => void run()} disabled={busy || text.trim().length < 3}>
          {busy ? "Reading..." : "Fill the form"}
        </button>
        <button type="button" className="btn btn-light" onClick={() => setText(EXAMPLE)}>Use example</button>
      </div>
      {error && <p className="warn small">{error}</p>}
      {result && (
        <div className="mt-s">
          {result.understood.length > 0 && (
            <div className="chips">{result.understood.map((u) => <span key={u} className="chip chip-on">{u}</span>)}</div>
          )}
          {result.notes.map((n) => <p key={n} className="small warn">{n}</p>)}
        </div>
      )}
    </section>
  );
}
