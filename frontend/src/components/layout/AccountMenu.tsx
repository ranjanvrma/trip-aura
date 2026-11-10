import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, ChevronRight, ListChecks, LogOut, MapPin, UserRound } from "lucide-react";
import { useAuth } from "../../lib/auth";
import { useSWR } from "../../lib/swr";
import { api } from "../../services/api";

/**
 * Account dropdown with a "Recent trips" submenu. Moving the pointer diagonally from the item to the submenu
 * keeps it open: an invisible triangle between the pointer and the submenu's near edge (the "safe triangle")
 * catches the pointer, so crossing a neighbouring item doesn't switch menus.
 */
export default function AccountMenu() {
  const { user, signOut } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState(false);
  const [tri, setTri] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const subRef = useRef<HTMLDivElement>(null);
  const trips = useSWR(user && open ? "trips" : null, api.listTrips);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  useEffect(() => { if (!open) { setSub(false); setTri(null); } }, [open]);

  // Recompute the triangle (pointer -> submenu top and bottom edge) as the pointer moves over the parent item.
  const onParentMove = (e: React.PointerEvent) => {
    // the triangle layer is position: fixed over the viewport, so viewport coordinates are used directly
    const menu = subRef.current?.getBoundingClientRect();
    if (!menu) return;
    const edge = menu.left > e.clientX ? menu.left : menu.right;
    setTri(`polygon(${e.clientX}px ${e.clientY}px, ${edge}px ${menu.top}px, ${edge}px ${menu.bottom}px)`);
  };

  if (!user) return <Link to="/signin" className="btn btn-ghost">Sign in</Link>;

  const go = (path: string) => { setOpen(false); nav(path, { viewTransition: true }); };

  return (
    <div className="menu" ref={root}>
      <button className="btn btn-ghost" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <UserRound size={16} aria-hidden /> <span className="truncate menu-email">{user.email}</span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className="menu-pop" role="menu">
          <div className="menu-item has-sub" role="menuitem" aria-haspopup="menu" aria-expanded={sub} tabIndex={0}
               onPointerEnter={() => setSub(true)} onPointerMove={onParentMove}
               onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "Enter") setSub(true); if (e.key === "ArrowLeft") setSub(false); }}>
            <MapPin size={15} aria-hidden /> Recent trips <ChevronRight size={14} className="ml-auto" aria-hidden />
            {sub && (
              <div className="menu-sub" role="menu" ref={subRef} onPointerEnter={() => setTri(null)}>
                {trips.loading && <div className="menu-note">Loading...</div>}
                {trips.data?.length === 0 && <div className="menu-note">No saved trips yet</div>}
                {trips.data?.slice(0, 6).map((t) => (
                  <button key={t.id} role="menuitem" className="menu-item" onClick={() => go(`/trips/${t.id}`)}>
                    <span className="truncate">{t.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          {sub && tri && <div className="safe-triangle" style={{ clipPath: tri }} onPointerEnter={() => setSub(true)} aria-hidden />}
          <button role="menuitem" className="menu-item" onPointerEnter={() => setSub(false)} onClick={() => go("/trips")}>
            <ListChecks size={15} aria-hidden /> All my trips
          </button>
          <button role="menuitem" className="menu-item" onPointerEnter={() => setSub(false)}
                  onClick={() => { setOpen(false); void signOut().then(() => nav("/")); }}>
            <LogOut size={15} aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
