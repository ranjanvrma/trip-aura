import type { DishSuggestion, FoodRecommendation } from "../../types";
import { moneyLabel, pretty } from "../../utils";
import { ExternalRatingBadge, SuitabilityBadge } from "./RatingBadges";

function Dish({ d }: { d: DishSuggestion }) {
  const label = d.status === "popular" ? `Popular · ${d.mention_count} reviews`
    : d.status === "mentioned" ? "Mentioned in 1 review"
    : d.status === "guide" ? "Named in travel guide" : "Suggestion";
  return (
    <li className={`dish dish-${d.status}`} title={d.evidence.join("\n") || "No review evidence - general suggestion for this cuisine"}>
      {d.name} <small>({label}{d.evidence_source === "mock" ? ", demo reviews" : ""})</small>
    </li>
  );
}

export default function RestaurantList({ recs, popular }: { recs: FoodRecommendation[]; popular: DishSuggestion[] }) {
  return (
    <section className="tile">
      <h2 className="tile-title">Food recommendations</h2>
      {popular.length > 0 && (
        <div className="mb-m">
          <h4>Local dishes</h4>
          <ul className="dishes">{popular.map((d) => <Dish key={d.name} d={d} />)}</ul>
          <p className="small muted">
            "Popular" means at least two separate reviews mention it; "travel guide" means Wikivoyage names it.
            Hover for the evidence. Dishes with unknown ingredients are hidden for strict diets.
          </p>
        </div>
      )}
      <div className="rest-grid">
        {recs.map((r) => (
          <article key={r.place.id} className="rest">
            <div className="row between wrap gap-s">
              <strong>{r.place.name}</strong>
              <span className="small muted">
                {r.place.avg_cost_per_person ? `${moneyLabel(r.place.avg_cost_per_person)} pp`
                  : r.place.price_level != null ? `${"$".repeat(Math.max(1, r.place.price_level))}${r.place.price_level_estimated ? " (est.)" : ""}` : ""}
              </span>
            </div>
            <div className="row wrap gap-s mt-xs">
              <ExternalRatingBadge rating={r.place.external_rating} hideEmpty />
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
