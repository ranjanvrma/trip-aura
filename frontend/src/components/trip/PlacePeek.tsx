import { useState } from "react";
import type { Place } from "../../types";
import { photoUrl } from "../../lib/placeLinks";

/** Wraps a place's name: on a mouse or pen hover (or keyboard focus) a small card shows the place's photo from
 *  Wikimedia Commons. The image is requested only once the card is first shown, and nothing appears for a place
 *  without one. Touch screens skip it: tapping the name opens the full details, which show the same photo. */
export default function PlacePeek({ place, children }: { place: Place; children: React.ReactNode }) {
  const [asked, setAsked] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!place.image || failed) return <>{children}</>;
  const ask = () => setAsked(true);
  return (
    <span className="peek" onPointerEnter={(e) => { if (e.pointerType !== "touch") ask(); }} onFocus={ask}>
      {children}
      {asked && (
        <span className="peek-card" aria-hidden>
          <img src={photoUrl(place.image, 330)} alt="" width={330} loading="lazy" decoding="async"
               referrerPolicy="no-referrer" onError={() => setFailed(true)} />
          <span className="peek-credit">Photo: Wikimedia Commons</span>
        </span>
      )}
    </span>
  );
}
