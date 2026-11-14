import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { usePageMeta } from "../lib/meta";

export default function NotFoundPage({ what = "page" }: { what?: "page" | "trip" }) {
  usePageMeta(what === "trip" ? "Trip not found" : "Page not found",
    "This page doesn't exist on TripAura.", { noindex: true });
  return (
    <div className="narrow">
      <section className="tile empty">
        <span className="empty-icon" aria-hidden><Compass size={26} /></span>
        <p className="eyebrow">404</p>
        <h1 className="h2">{what === "trip" ? "We couldn't find that trip" : "This page doesn't exist"}</h1>
        <p className="muted">
          {what === "trip"
            ? "It may have been deleted, or it was saved in another browser or on another device."
            : "The link may be mistyped or out of date."}
        </p>
        <div className="row gap-s wrap center">
          <Link to="/" className="btn btn-primary" viewTransition>Plan a trip</Link>
          <Link to="/trips" className="btn btn-ghost" viewTransition>My trips</Link>
        </div>
      </section>
    </div>
  );
}
