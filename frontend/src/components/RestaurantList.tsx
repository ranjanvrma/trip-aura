import type { DishSuggestion, FoodRecommendation } from "../types";
import { moneyLabel, pretty } from "../utils";
import { ExternalRatingBadge, SuitabilityBadge } from "./RatingBadges";

function Dish({ d }: { d: DishSuggestion }) {
  const label = d.status === "popular" ? `Popular · ${d.mention_count} reviews`
    : d.status === "mentioned" ? "Mentioned in 1 review" : "Suggestion";
  return (
    <li className={`dish dish-${d.status}`} title={d.evidence.join("\n") || "No review evidence - general suggestion for this cuisine"}>
      {d.name} <small>({label}{d.evidence_source === "mock" ? ", demo reviews" : ""})</small>
    </li>
  );
}

export default function RestaurantList({ recs, popular }: { recs: FoodRecommendation[]; popular: DishSuggestion[] }) {
  return (
    <section className="card">
      <h3>Food recommendations</h3>
      {popular.length > 0 && (
        <div className="mb-m">
          <h4>Dishes popular across reviews</h4>
          <ul className="dishes">{popular.map((d) => <Dish key={d.name} d={d} />)}</ul>
          <p className="small muted">"Popular" means at least two separate reviews mention it. Hover for the evidence.</p>
        </div>
      )}
      <div className="rest-grid">
        {recs.map((r) => (
          <article key={r.place.id} className="rest">
            <div className="row between wrap gap-s">
              <strong>{r.place.name}</strong>
              <span className="small muted">{moneyLabel(r.place.avg_cost_per_person)} pp</span>
            </div>
            <div className="row wrap gap-s mt-xs">
              <ExternalRatingBadge rating={r.place.external_rating} />
              <SuitabilityBadge score={r.suitability} />
            </div>
            <p className="small muted mt-xs">
              {r.place.food_categories.map(pretty).join(", ")}{r.meal_types.length ? ` · ${r.meal_types.join(", ")}` : ""}
            </p>
            <p className="small">{r.diet_match.join(" · ")}</p>
            {r.dishes.length > 0 && <ul className="dishes">{r.dishes.map((d) => <Dish key={d.name} d={d} />)}</ul>}
          </article>
        ))}
      </div>
    </section>
  );
}
