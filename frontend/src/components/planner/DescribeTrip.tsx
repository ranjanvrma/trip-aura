import { useState } from "react";
import { api, ApiError } from "../../services/api";
import type { ParsedTrip } from "../../types";

const EXAMPLE = "4 days in Lisbon with my partner from 12 Dec, vegetarian, we love museums, street art and sunsets, "
  + "budget 900 euros, staying at Rossio, relaxed pace, metro and walking";

/** Free-text trip description -> form fields (backend NLP parser). */
export default function DescribeTrip({ onParsed }: { onParsed: (p: ParsedTrip) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ParsedTrip | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canRun = text.trim().length >= 3 && !busy;

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
      <h2 className="h1"><label htmlFor="describe-text">Or just say it</label></h2>
      <textarea id="describe-text" rows={3} maxLength={500} value={text} onChange={(e) => setText(e.target.value)}
                placeholder={EXAMPLE} aria-describedby="describe-help"
                onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && canRun) void run(); }} />
      <div className="describe-actions">
        <p id="describe-help" className="small muted">Dates, budget, who's going, what you like. It fills in the planner for you.</p>
        <button type="button" className="link" onClick={() => setText(EXAMPLE)}>Try an example</button>
        <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={!canRun}>
          {busy ? <><span className="spinner" aria-hidden /> Reading</> : "Fill in the planner"}
        </button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      {result && (
        <div className="mt-s" role="status">
          {result.understood.length > 0 && (
            <ul className="understood" aria-label="What we picked up">
              {result.understood.map((u) => <li key={u}>{u}</li>)}
            </ul>
          )}
          {result.notes.map((n) => <p key={n} className="small warn">{n}</p>)}
        </div>
      )}
    </section>
  );
}
