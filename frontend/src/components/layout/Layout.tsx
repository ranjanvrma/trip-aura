import { motion, useScroll, useSpring } from "motion/react";
import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { CodeXml, Menu, Moon, Search, Sun } from "lucide-react";
import { modKey } from "../../lib/platform";
import { toggleTheme, useTheme } from "../../lib/theme";
import { useCommands } from "./CommandMenu";
import Sheet from "../ui/Sheet";
import Kbd from "../ui/Kbd";
import Logo from "./Logo";

export const REPO_URL = "https://github.com/ranjanvrma/trip-aura";

const AUTHORS = [
  { name: "Ranjan Verma", github: "https://github.com/ranjanvrma", linkedin: "https://www.linkedin.com/in/ranjan-vrma/" },
  { name: "Chinmay Dahiya", github: "https://github.com/dahiyachinmay15", linkedin: "https://www.linkedin.com/in/chinmaydahiya/" },
];

/** Warm the route's code chunk on hover or focus, so the next page appears without a wait. */
const preload: Record<string, () => Promise<unknown>> = {
  "/trips": () => import("../../pages/TripsPage"),
  "/terms": () => import("../../pages/LegalPages"),
  "/privacy": () => import("../../pages/LegalPages"),
};
const warm = (path: string) => () => { void preload[path]?.(); };

const LINKS = [
  { to: "/", label: "Home" },
  { to: "/trips", label: "My trips" },
];

function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 260, damping: 40, restDelta: 0.001 });
  return <motion.div className="scroll-progress" style={{ scaleX }} aria-hidden />;
}

export default function Layout({ banner }: { banner?: React.ReactNode }) {
  const { open } = useCommands();
  const [menu, setMenu] = useState(false);
  const closeMenu = () => setMenu(false);
  const theme = useTheme();
  const other = theme === "dark" ? "light" : "dark";
  const ThemeIcon = theme === "dark" ? Sun : Moon;

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
            <button className="icon-btn hit theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${other} theme`} title={`Switch to ${other} theme`}>
              <ThemeIcon size={18} aria-hidden />
            </button>
            <Link to="/#plan" className="btn btn-cta nav-cta" viewTransition>Plan a trip</Link>
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
          <Link to="/terms" className="mobile-link" onClick={closeMenu}>Terms of use</Link>
          <Link to="/privacy" className="mobile-link" onClick={closeMenu}>Privacy policy</Link>
          <button type="button" className="mobile-link" onClick={toggleTheme}>
            <ThemeIcon size={18} aria-hidden /> Switch to {other} theme
          </button>
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
            <p className="muted">Day-by-day trip plans for any city, built from open map data.</p>
          </div>
          <nav className="footer-col" aria-label="Product">
            <h2>Product</h2>
            <Link to="/#plan">Plan a trip</Link>
            <Link to="/trips" onPointerEnter={warm("/trips")}>My trips</Link>
            <a href={`${REPO_URL}/releases`} target="_blank" rel="noopener noreferrer" className="footer-version">
              Version {__APP_VERSION__}
            </a>
          </nav>
          <nav className="footer-col" aria-label="Project">
            <h2>Project</h2>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer"><CodeXml size={14} aria-hidden /> Source code</a>
            <a href={`${REPO_URL}/issues`} target="_blank" rel="noopener noreferrer">Contact and support</a>
            <Link to="/terms" onPointerEnter={warm("/terms")}>Terms of use</Link>
            <Link to="/privacy" onPointerEnter={warm("/privacy")}>Privacy policy</Link>
          </nav>
          <div className="footer-col">
            <h2>Made by</h2>
            <ul className="footer-people">
              {AUTHORS.map((a) => (
                <li key={a.name}>
                  <span>{a.name}</span>
                  <a href={a.github} target="_blank" rel="noopener noreferrer" aria-label={`${a.name} on GitHub`}>GitHub</a>
                  <a href={a.linkedin} target="_blank" rel="noopener noreferrer" aria-label={`${a.name} on LinkedIn`}>LinkedIn</a>
                </li>
              ))}
            </ul>
          </div>
          <p className="footer-word" aria-hidden>TripAura</p>
          <p className="footer-legal small muted">
            © {new Date().getFullYear()} Ranjan Verma and Chinmay Dahiya. Map data © OpenStreetMap contributors (ODbL),
            Overture Maps Foundation, Wikidata (CC0), Wikivoyage (CC BY-SA), GeoNames (CC BY). Earth imagery: NASA.
          </p>
        </div>
      </footer>
    </div>
  );
}
