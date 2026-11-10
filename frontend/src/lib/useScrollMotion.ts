import { useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { prefersReducedMotion } from "./safeUrl";

gsap.registerPlugin(ScrollTrigger);

/**
 * Restrained scroll feedback inside `root`:
 * - `[data-reveal]` tiles fade and lift slightly the first time they come into view (once each; tiles already
 *   on screen are shown immediately, and a tile is never left hidden);
 * - `[data-parallax="0.12"]` elements drift by that fraction while they scroll past.
 * Everything is off for people who prefer reduced motion.
 */
export function useScrollMotion(root: React.RefObject<HTMLElement | null>, deps: unknown[] = []) {
  useLayoutEffect(() => {
    const el = root.current;
    if (!el || prefersReducedMotion()) return;

    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        io.unobserve(e.target);
        gsap.to(e.target, { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: "power2.out", overwrite: true,
                            clearProps: "transform,opacity" });
      }
    }, { rootMargin: "0px 0px -6% 0px" });

    const tiles = Array.from(el.querySelectorAll<HTMLElement>("[data-reveal]:not([data-revealed])"));
    for (const t of tiles) {
      t.dataset.revealed = "";
      const r = t.getBoundingClientRect();
      if (r.top < window.innerHeight) continue;          // already visible: never hide it
      gsap.set(t, { opacity: 0, y: 16, scale: 0.99 });
      io.observe(t);
    }

    const ctx = gsap.context(() => {
      gsap.utils.toArray<HTMLElement>("[data-parallax]").forEach((p) => {
        const f = Number(p.dataset.parallax) || 0.1;
        gsap.fromTo(p, { yPercent: -f * 50 }, {
          yPercent: f * 50, ease: "none",
          scrollTrigger: { trigger: p, start: "top bottom", end: "bottom top", scrub: 0.4 },
        });
      });
    }, el);

    return () => {
      io.disconnect();
      ctx.revert();
      // anything still waiting becomes visible, so a re-run can never leave a tile hidden
      gsap.set(tiles.filter((t) => t.style.opacity === "0"), { clearProps: "transform,opacity" });
      tiles.forEach((t) => delete t.dataset.revealed);
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}
