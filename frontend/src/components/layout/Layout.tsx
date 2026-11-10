import { motion, useScroll, useSpring } from "motion/react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { CodeXml, Menu, Search } from "lucide-react";
import { useAuth } from "../../lib/auth";
import { modKey } from "../../lib/platform";
import { useCommands } from "../CommandMenu";
import Sheet from "../ui/Sheet";
import { Kbd } from "../ui/Skeleton";
import AccountMenu from "./AccountMenu";
import Logo from "./Logo";

export const REPO_URL = "https://github.com/ranjanvrma/trip-aura";

/** Warm the route's code chunk on hover or focus, so the next page appears without a wait. */
const preload: Record<string, () => Promise<unknown>> = {
  "/trips": () => import("../../pages/TripsPage"),
  "/signin": () => import("../../pages/SignInPage"),
  "/terms": () => import("../../pages/LegalPages"),
  "/privacy": () => import("../../pages/LegalPages"),
};
const warm = (path: string) => () => { void preload[path]?.(); };

const LINKS = [
  { to: "/", label: "Plan a trip" },
  { to: "/trips", label: "My trips" },
];

function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 260, damping: 40, restDelta: 0.001 });
  return <motion.div className="scroll-progress" style={{ scaleX }} aria-hidden />;
}

export default function Layout({ banner }: { banner?: React.ReactNode }) {
  const { open } = useCommands();
  const { user, signOut } = useAuth();
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  const closeMenu = () => setMenu(false);

  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <ScrollProgress />
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand" viewTransition aria-label="TripAura home"><Logo /> <span>TripAura</span></Link>
          <nav className="nav-desktop" aria-label="Main">
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} end viewTransition onPointerEnter={warm(l.to)} onFocus={warm(l.to)}
                       className={({ isActive }) => `nav-link ${isActive ? "is-active" : ""}`}>{l.label}</NavLink>
            ))}
          </nav>
          <div className="topbar-actions">
            <button className="btn btn-ghost cmd-trigger" onClick={open} aria-label="Open command menu" aria-keyshortcuts="Control+K Meta+K">
              <Search size={16} aria-hidden /> <span className="cmd-trigger-text">Search</span>
              <span className="kbd-group" aria-hidden><Kbd>{modKey()}</Kbd><Kbd>K</Kbd></span>
            </button>
            <div className="nav-desktop"><AccountMenu /></div>
            <button className="icon-btn hit nav-mobile" onClick={() => setMenu(true)} aria-label="Open menu" aria-expanded={menu}>
              <Menu size={20} aria-hidden />
            </button>
          </div>
        </div>
      </header>

      <Sheet open={menu} onClose={closeMenu} title="Menu">
        <nav className="mobile-nav" aria-label="Mobile">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end viewTransition onClick={closeMenu}
                     className={({ isActive }) => `mobile-link ${isActive ? "is-active" : ""}`}>{l.label}</NavLink>
          ))}
          {user
            ? (
              <>
                <p className="muted small mobile-signed">Signed in as {user.email}</p>
                <button className="mobile-link mobile-btn" onClick={() => { closeMenu(); void signOut(); }}>Sign out</button>
              </>
            )
            : <Link to={`/signin?next=${encodeURIComponent(loc.pathname)}`} className="mobile-link" onClick={closeMenu}>Sign in</Link>}
          <Link to="/terms" className="mobile-link" onClick={closeMenu}>Terms of use</Link>
          <Link to="/privacy" className="mobile-link" onClick={closeMenu}>Privacy policy</Link>
        </nav>
      </Sheet>

      {banner}
      <main id="main" className="main" tabIndex={-1}>
        <Outlet />
      </main>

      <footer className="footer">
        <div className="footer-inner">
          <div className="footer-brand">
            <Link to="/" className="brand"><Logo /> <span>TripAura</span></Link>
            <p className="muted small">Day-by-day trip plans from open map data. Built by Ranjan Verma and Chinmay Dahiya.</p>
          </div>
          <nav className="footer-links" aria-label="Footer">
            <Link to="/terms" onPointerEnter={warm("/terms")}>Terms of use</Link>
            <Link to="/privacy" onPointerEnter={warm("/privacy")}>Privacy policy</Link>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer"><CodeXml size={14} aria-hidden /> Source code</a>
            <a href={`${REPO_URL}/issues`} target="_blank" rel="noopener noreferrer">Contact and support</a>
          </nav>
          <p className="footer-legal small muted">
            © {new Date().getFullYear()} Ranjan Verma and Chinmay Dahiya. Map data © OpenStreetMap contributors (ODbL),
            Overture Maps Foundation, Wikidata (CC0), Wikivoyage (CC BY-SA), GeoNames (CC BY).
          </p>
        </div>
      </footer>
    </div>
  );
}
