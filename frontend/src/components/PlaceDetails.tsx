import { ExternalLink, X } from "lucide-react";
import { safeExternalUrl } from "../lib/safeUrl";
import type { ItineraryItem } from "../types";
import { moneyLabel, pretty } from "../utils";
import { ExternalRatingBadge, ScoreBreakdown, SuitabilityBadge } from "./RatingBadges";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const SOURCE_LABEL: Record<string, string> = {
  osm: "OpenStreetMap", overture: "Overture Maps", wikidata: "Wikidata", google: "Google Maps Platform",
  mock: "Demo dataset (mock)",
};
const OSM_TYPE: Record<string, string> = { n: "node", w: "way", r: "relation" };

export default function PlaceDetails({ item, onClose, embedded = false }: { item: ItineraryItem; onClose: () => void; embedded?: boolean }) {
  const p = item.place;
  if (!p) return null;
  const fee = item.type === "meal" ? p.avg_cost_per_person : p.entry_fee;
  const maps = safeExternalUrl(p.google_maps_uri);
  const wikidata = p.external_ids?.wikidata && /^Q\d+$/.test(p.external_ids.wikidata) ? p.external_ids.wikidata : null;
  const osm = p.external_ids?.osm && /^[nwr]\d+$/.test(p.external_ids.osm) ? p.external_ids.osm : null;
  const tags = p.categories.filter((c) => !c.startsWith("search:") && c !== "food");
  return (
    <aside className={embedded ? "details" : "tile details"} aria-label={`Details for ${p.name}`}>
      {!embedded && (
        <div className="tile-head">
          <h2 className="h3">{p.name}</h2>
          <button className="icon-btn hit" onClick={onClose} aria-label="Close details"><X size={18} aria-hidden /></button>
        </div>
      )}
      {p.description && <p>{p.description}</p>}
      {p.address && <p className="small muted">{p.address}</p>}

      <div className="two-ratings">
        <div>
          <div className="small muted">External rating</div>
          <ExternalRatingBadge rating={p.external_rating} />
          <div className="small muted">{p.external_rating?.label}</div>
        </div>
        <div>
          <div className="small muted">Your suitability</div>
          <SuitabilityBadge score={item.suitability} />
          <div className="small muted">TripAura's own score - not a review rating</div>
        </div>
      </div>

      {item.suitability && (
        <>
          <h4>Why it matches you</h4>
          <ul className="reasons">{item.suitability.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <ScoreBreakdown score={item.suitability} />
        </>
      )}

      <h4>Practical info</h4>
      <ul className="small">
        <li>Scheduled: {item.start}-{item.end} ({item.duration_min} min)</li>
        {fee && <li>{item.type === "meal" ? "Avg. cost per person" : "Entry fee per person"}: {moneyLabel(fee)}
          {" "}<span className="muted">({fee.verified ? "verified" : fee.note ?? "estimate"})</span></li>}
        {!fee && item.type === "activity" && <li>Entry fee: not published - {moneyLabel(item.cost)} assumed</li>}
        {tags.length > 0 && <li>Tags: {tags.map(pretty).join(", ")}</li>}
        {p.cuisines.length > 0 && <li>Cuisine: {p.cuisines.map(pretty).join(", ")}</li>}
      </ul>

      {p.opening_hours && (
        p.opening_hours.known ? (
          <table className="hours small">
            <tbody>
              {DAYS.map((d, i) => {
                const r = p.opening_hours!.weekly[String(i)] ?? [];
                return <tr key={d}><td>{d}</td><td>{r.length ? r.map((x) => `${x.open}-${x.close}`).join(", ") : "Closed"}</td></tr>;
              })}
            </tbody>
          </table>
        ) : <p className="small warn">Opening hours not available in the data - check before visiting.</p>
      )}
      {p.reviews.length > 0 && (
        <>
          <h4>Reviews <span className="muted small">({p.reviews[0].source === "google" ? "from Google" : "demo reviews"})</span></h4>
          <ul className="small reviews">{p.reviews.slice(0, 3).map((r) => <li key={r.text}>"{r.text}"</li>)}</ul>
        </>
      )}
      <p className="small muted">
        Data source: {SOURCE_LABEL[p.source] ?? p.source}
        {p.prominence ? " · covered by " + p.prominence + " Wikipedia editions" : ""}
      </p>
      <div className="row gap-m wrap small">
        {maps && <a href={maps} target="_blank" rel="noopener noreferrer">Google Maps <ExternalLink size={12} aria-hidden /></a>}
        {wikidata && (
          <a href={`https://www.wikidata.org/wiki/${wikidata}`} target="_blank" rel="noopener noreferrer">Wikidata <ExternalLink size={12} aria-hidden /></a>
        )}
        {osm && (
          <a href={`https://www.openstreetmap.org/${OSM_TYPE[osm[0]]}/${osm.slice(1)}`}
             target="_blank" rel="noopener noreferrer">OpenStreetMap <ExternalLink size={12} aria-hidden /></a>
        )}
      </div>
    </aside>
  );
}
