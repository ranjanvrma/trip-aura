import { Star } from "lucide-react";
import type { ExternalRating, SuitabilityScore } from "../../types";

/**
 * External (Google or demo) rating. Always shown separately from our suitability score.
 * In lists, `hideEmpty` leaves unrated places without a badge (the place details still say "No rating").
 */
export function ExternalRatingBadge({ rating, hideEmpty = false }: { rating?: ExternalRating | null; hideEmpty?: boolean }) {
  if (!rating || rating.rating == null) {
    if (hideEmpty) return null;
    return (
      <span className="badge badge-muted" title={rating?.label ?? "Open data has no ratings and no Google match was found"}>
        No rating
      </span>
    );
  }
  const google = rating.provider === "google" && rating.verified;
  return (
    <span className={`badge ${google ? "badge-google" : "badge-mock"}`} title={rating.label}>
      {google ? "Google" : "Demo"} <Star size={11} aria-hidden className="star" /> <span className="num">{rating.rating.toFixed(1)}</span>
      {rating.review_count != null && <span className="muted"> ({rating.review_count.toLocaleString()})</span>}
    </span>
  );
}

export function SuitabilityBadge({ score }: { score?: SuitabilityScore | null }) {
  if (!score) return null;
  const tone = score.score >= 4 ? "good" : score.score >= 3 ? "ok" : "low";
  return (
    <span className={`badge badge-fit badge-fit-${tone}`} title="TripAura suitability score - personalised to your trip">
      Fit {score.score.toFixed(1)}/5
    </span>
  );
}

export function ScoreBreakdown({ score }: { score: SuitabilityScore }) {
  return (
    <div className="breakdown">
      {Object.entries(score.components).map(([k, v]) => (
        <div key={k} className="bar-row">
          <span className="bar-label">{k}</span>
          <span className="bar"><span style={{ width: `${Math.round(v * 100)}%` }} /></span>
          <span className="bar-val">{Math.round(v * 100)}%</span>
          <span className="muted small">x{score.weights[k]}</span>
        </div>
      ))}
    </div>
  );
}
