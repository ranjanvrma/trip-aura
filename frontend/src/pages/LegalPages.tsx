import { Link } from "react-router-dom";
import { REPO_URL } from "../components/layout/Layout";
import { usePageMeta } from "../lib/meta";

const UPDATED = "10 November 2026";
const OPERATORS = "Ranjan Verma and Chinmay Dahiya";

function LegalShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <article className="page legal">
      <header className="legal-head">
        <p className="eyebrow">Legal</p>
        <h1 className="h1">{title}</h1>
        <p className="muted small">Last updated {UPDATED}</p>
      </header>
      <div className="legal-body">{children}</div>
    </article>
  );
}

export function TermsPage() {
  usePageMeta("Terms of use", "The terms for using TripAura, a free day-by-day trip planner.");
  return (
    <LegalShell title="Terms of use">
      <p>
        TripAura is a free trip-planning tool run by {OPERATORS} (“we”). By using it you agree to these terms.
        If you don't agree, please don't use the service.
      </p>

      <h2>What TripAura does</h2>
      <p>
        TripAura builds suggested day-by-day itineraries from open map data (Overture Maps, Wikidata, OpenStreetMap,
        Wikivoyage and GeoNames). Opening hours, prices, travel times and ratings can be missing, out of date or wrong.
        Estimates are marked as estimates. Always check important details, such as opening times, tickets, safety and
        transport, with the official source before you travel.
      </p>

      <h2>Your saved trips</h2>
      <p>Trips are saved in this browser on this device. They do not sync to other devices. Anyone using the same browser profile may be able to see them. Clearing this website's browser storage deletes saved trips.</p>

      <h2>Acceptable use</h2>
      <p>Don't misuse the service. In particular, don't:</p>
      <ul>
        <li>try to access other people's trips or accounts, or probe, scan or break the service's security;</li>
        <li>send automated traffic that overloads the service or the open-data providers it relies on;</li>
        <li>use TripAura for anything unlawful.</li>
      </ul>
      <p>We limit request rates and may suspend access that breaks these rules.</p>

      <h2>Map data and licences</h2>
      <p>
        Place data remains under its original licences: OpenStreetMap (ODbL), Overture Maps Foundation, Wikidata (CC0),
        Wikivoyage (CC BY-SA) and GeoNames (CC BY). Exchange rates come from the European Central Bank (through
        Frankfurter) and, for other currencies, ExchangeRate-API. Every itinerary lists its sources. The TripAura source code is
        available on <a href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub</a>.
      </p>

      <h2>No warranty</h2>
      <p>
        TripAura is provided “as is”, free of charge and without guarantees of availability or accuracy. As far as
        the law allows, we aren't liable for losses that come from relying on a suggested plan, such as a closed venue,
        a missed connection or a price that differs from the estimate.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. The date above shows the latest version. If you keep using TripAura after a change,
        you accept the updated terms.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms can be raised as an issue on the{" "}
        <a href={`${REPO_URL}/issues`} target="_blank" rel="noopener noreferrer">project's GitHub page</a>.
        Please don't post personal information there.
      </p>
    </LegalShell>
  );
}

export function PrivacyPage() {
  usePageMeta("Privacy policy", "What TripAura stores, why, for how long, and who it is shared with.");
  return (
    <LegalShell title="Privacy policy">
      <p>
        This policy explains what TripAura, run by {OPERATORS}, collects and why. We collect as little as we can,
        we don't sell data, and we don't use advertising or analytics trackers.
      </p>

      <h2>What we store</h2>
      <table className="table legal-table">
        <thead><tr><th>Data</th><th>Why</th><th>How long</th></tr></thead>
        <tbody>
          <tr><td>Trip request and itinerary</td><td>Saved in your browser so you can reopen your plan</td><td>Until you delete it or clear this website's browser storage</td></tr>
        </tbody>
      </table>

      <h2>What we don't store</h2>
      <ul>
        <li><strong>IP addresses.</strong> They're used briefly in server memory to limit request rates, and aren't written to the database.</li>
      </ul>

      <h2>Cookies and browser storage</h2>
      <p>
        Saved trips use your browser's local storage. They stay on this device and browser profile, and are removed if you delete them or clear site data. There are no advertising or analytics cookies.
      </p>

      <h2>Services that process data for us</h2>
      <ul>
        <li><strong>Hosting provider</strong> runs the website and API. When you generate a plan, the trip details are sent to the API to build it; the generated itinerary is returned to your browser and saved there.</li>
        <li>
          <strong>Map tiles</strong> are loaded by your browser from the OpenStreetMap tile servers (or Google Maps, if
          enabled). Those servers see your IP address and the map area you view.
        </li>
        <li>
          <strong>Open-data lookups.</strong> To build a plan, our server queries services such as Overture Maps,
          Wikidata, OpenStreetMap (Overpass and Nominatim), Photon and Wikivoyage with the city or address you
          typed. These requests contain nothing that identifies you. Exchange rates are loaded from Frankfurter and
          ExchangeRate-API, and those requests contain nothing about you or your trip.
        </li>
      </ul>

      <h2>Your choices and rights</h2>
      <ul>
        <li>Delete any trip from <Link to="/trips">My trips</Link>, or clear this website's storage in your browser settings.</li>
        <li>Depending on where you live, you may have rights to access, correct or erase your data.</li>
      </ul>

      <h2>Security</h2>
      <p>
        Connections are encrypted (HTTPS). Requests are rate limited. Trips saved in local storage can be viewed by anyone who can use the same browser profile.
      </p>

      <h2>Children</h2>
      <p>TripAura isn't intended for children under 13, and we don't knowingly collect their data.</p>

      <h2>Changes and contact</h2>
      <p>
        If this policy changes, the date above changes too. Questions can be raised on the{" "}
        <a href={`${REPO_URL}/issues`} target="_blank" rel="noopener noreferrer">project's GitHub page</a>.
        Please don't post personal information there.
      </p>
    </LegalShell>
  );
}
