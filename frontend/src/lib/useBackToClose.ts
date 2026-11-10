import { useEffect, useRef } from "react";

let seq = 0;

/**
 * Predictive back for overlays: opening a sheet or menu adds a history entry, so the system back gesture
 * (Android predictive back, iOS swipe, browser back) closes the overlay instead of leaving the page.
 */
export function useBackToClose(open: boolean, onClose: () => void) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const token = ++seq;
    window.history.pushState({ ...(window.history.state ?? {}), overlay: token }, "");
    let poppedByBack = false;
    const onPop = () => { poppedByBack = true; closeRef.current(); };
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("popstate", onPop);
      // Closed by a button, Escape or swipe: remove the entry we added. If a link inside the overlay already
      // navigated somewhere else, our entry is no longer current and must not be popped (that would undo the navigation).
      if (!poppedByBack && window.history.state?.overlay === token) window.history.back();
    };
  }, [open]);
}
