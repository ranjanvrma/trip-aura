import { Plane } from "lucide-react";
import type { TripRequest, TripStyle } from "../../types";
import { cityMark, fmtDay, fmtMoney, pretty } from "../../utils";

const STYLE_LABEL: Record<TripStyle, string> = { budget: "Lowest cost", mid: "Mid-range", premium: "Premium" };

/** One labelled value; it re-mounts when the value changes, which replays the small settle animation. */
function Cell({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "pass-wide" : undefined}>
      <dt>{label}</dt>
      <dd key={value} className={value === "—" ? "is-empty" : undefined}>{value}</dd>
    </div>
  );
}

/**
 * The trip so far, drawn as a boarding pass that fills in while the traveller answers. It shows only what was
 * entered: nothing here is estimated or invented.
 */
export default function BoardingPass({ req, step, steps }: { req: TripRequest; step: number; steps: number }) {
  const city = req.destination_city.split(",")[0].trim();
  const rest = req.destination_city.split(",").slice(1).join(",").trim();
  const stay = req.accommodation.name_or_address.split(",")[0].trim();
  const interests = req.interests.slice(0, 3).map(pretty).join(", ") + (req.interests.length > 3 ? ` +${req.interests.length - 3}` : "");

  return (
    <aside className="pass" aria-label="Your trip so far">
      <header className="pass-top">
        <span className="pass-brand">TripAura</span>
        <span className="pass-step num">Step {step + 1} of {steps}</span>
      </header>

      <div className="pass-route">
        <div>
          <span className="pass-label">Staying at</span>
          <strong key={stay} className={`pass-place ${stay ? "" : "is-empty"}`}>{stay || "Your stay"}</strong>
        </div>
        <span className="pass-line" aria-hidden><Plane size={18} /></span>
        <div className="pass-to">
          <span className="pass-label">Destination</span>
          <strong key={city} className={`pass-code ${city ? "" : "is-empty"}`}>{city ? cityMark(city) : "· · ·"}</strong>
          <span className="pass-city">{city || "Pick a city"}{rest && <span className="muted">, {rest}</span>}</span>
        </div>
      </div>

      <dl className="pass-grid">
        <Cell label="From" value={req.start_date ? fmtDay(req.start_date) : "—"} />
        <Cell label="Days" value={String(req.num_days)} />
        <Cell label="Travellers" value={String(req.travelers)} />
        <Cell label="Budget" value={req.budget > 0 ? fmtMoney(req.budget, req.currency) : "—"} />
        <Cell label="Style" value={STYLE_LABEL[req.trip_style ?? "mid"]} />
        <Cell label="Pace" value={pretty(req.pace)} />
        <Cell label="Into" value={interests || "—"} wide />
      </dl>

      <footer className="pass-foot">
        <span className="pass-barcode" aria-hidden />
        <span className="small">Kept in this browser only</span>
      </footer>
    </aside>
  );
}
