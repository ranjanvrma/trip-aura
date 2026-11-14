import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../../lib/platform";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

interface Props {
  words: string[];               // shown in turn, upper-cased; longer ones are cut to `cells`
  cells: number;
  onPick: (word: string) => void;
  holdMs?: number;
}

/**
 * A departure-board row that flips through destination names. Each cell runs through a few letters before it
 * lands, the way a split-flap board does. Clicking it picks the city on show. With reduced motion the names
 * simply swap. Screen readers get one stable label instead of the flipping letters.
 */
export default function SplitFlap({ words, cells, onPick, holdMs = 3200 }: Props) {
  const [index, setIndex] = useState(0);
  const [chars, setChars] = useState(() => pad(words[0], cells));
  const paused = useRef(false);

  useEffect(() => {
    const t = window.setInterval(() => { if (!paused.current && !document.hidden) setIndex((i) => (i + 1) % words.length); }, holdMs);
    return () => window.clearInterval(t);
  }, [words.length, holdMs]);

  useEffect(() => {
    const target = pad(words[index % words.length], cells);
    if (prefersReducedMotion()) { setChars(target); return; }
    let frame = 0;
    const t = window.setInterval(() => {
      frame += 1;
      // cell i settles after 4 + 2i ticks, so the word resolves left to right
      setChars(target.map((ch, i) => (frame >= 4 + i * 2 || ch === " " ? ch : LETTERS[(frame * 7 + i * 11) % LETTERS.length])));
      if (frame >= 4 + cells * 2) window.clearInterval(t);
    }, 45);
    return () => window.clearInterval(t);
  }, [index, words, cells]);

  const word = words[index % words.length];   // the list can shrink (demo mode) while the index is ahead
  return (
    <button type="button" className="flap" onClick={() => onPick(word)} aria-label={`Plan a trip to ${word}`}
            onPointerEnter={() => { paused.current = true; }} onPointerLeave={() => { paused.current = false; }}
            onFocus={() => { paused.current = true; }} onBlur={() => { paused.current = false; }}>
      {chars.map((ch, i) => (
        <span key={i} className={`flap-cell ${ch === " " ? "is-blank" : ""}`} aria-hidden>
          <span key={ch} className="flap-char">{ch}</span>
        </span>
      ))}
    </button>
  );
}

function pad(word: string, cells: number): string[] {
  return word.toUpperCase().slice(0, cells).padEnd(cells, " ").split("");
}
