import type { GeoState } from "../hooks/useGeolocation";
import type { LiveProgress, TransportAlert } from "../types";
import { MODE_LABEL, moneyLabel } from "../utils";

interface Props {
  enabled: boolean;
  onToggle: (v: boolean) => void;
  geo: GeoState;
  progress: LiveProgress | null;
  alerts: (TransportAlert & { at: string })[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  targets: { id: string; label: string }[];
  targetId: string | null;
  onTarget: (id: string | null) => void;
}

export default function LiveLocationPanel(p: Props) {
  const askNotify = () => { if ("Notification" in window) void Notification.requestPermission(); };
  return (
    <section className="card">
      <div className="row between wrap gap-s">
        <h3>Live location</h3>
        <label className="switch">
          <input type="checkbox" checked={p.enabled} onChange={(e) => p.onToggle(e.target.checked)} />
          <span>{p.enabled ? "On" : "Off"}</span>
        </label>
      </div>
      <p className="small muted">
        Uses your browser's location only while switched on. Positions are sent to the backend to refresh
        travel estimates and are not stored. Turning it off stops tracking immediately.
      </p>
      {p.geo.permission === "denied" && <p className="warn small">Location permission is blocked for this site.</p>}
      {p.geo.error && <p className="warn small">{p.geo.error}</p>}
      {p.enabled && (
        <>
          <label className="field">
            <span>Heading to</span>
            <select value={p.targetId ?? ""} onChange={(e) => p.onTarget(e.target.value || null)}>
              <option value="">Next stop by time of day</option>
              {p.targets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          {!p.geo.position && !p.geo.error && <p className="small">Waiting for your position...</p>}
          {p.geo.position && (
            <p className="small">
              You: {p.geo.position.lat.toFixed(5)}, {p.geo.position.lng.toFixed(5)}
              {p.geo.accuracy != null && ` (±${Math.round(p.geo.accuracy)} m)`}
            </p>
          )}
          {p.progress?.next_place_name && (
            <div className="live-box">
              <div><strong>{p.progress.next_place_name}</strong> - {p.progress.straight_line_km?.toFixed(2)} km straight-line</div>
              {p.progress.recommended && (
                <div className="small">
                  Best now: {MODE_LABEL[p.progress.recommended.mode]}, {Math.round(p.progress.recommended.duration_min)} min,
                  {" "}{moneyLabel(p.progress.recommended.cost)}
                  {p.progress.recommended.traffic_aware ? (p.progress.data_source === "mock" ? " (simulated traffic)" : " (live traffic)") : ""}
                </div>
              )}
              <ul className="small">
                {p.progress.options.map((o) => (
                  <li key={o.mode} className={o.practical ? "" : "muted"}>
                    {o.duration_min === 0 && !o.practical
                      ? <>{MODE_LABEL[o.mode]}: not available ({o.note})</>
                      : <>{MODE_LABEL[o.mode]}: {Math.round(o.duration_min)} min · {o.distance_km.toFixed(1)} km · {moneyLabel(o.cost)}
                          {!o.practical && ` (not practical${o.note ? `: ${o.note}` : ""})`}</>}
                  </li>
                ))}
              </ul>
              <div className="small muted">Checked {p.progress.checked_at.slice(11)}</div>
            </div>
          )}
          <div className="row gap-s wrap">
            <button className="btn btn-light" onClick={p.onRefresh} disabled={p.loading || !p.geo.position}>
              {p.loading ? "Refreshing..." : "Refresh estimates"}
            </button>
            {"Notification" in window && Notification.permission === "default" && (
              <button className="btn btn-light" onClick={askNotify}>Enable notifications</button>
            )}
          </div>
          {p.error && <p className="warn small">{p.error}</p>}
        </>
      )}
      {p.alerts.length > 0 && (
        <ul className="alerts">
          {p.alerts.map((a, i) => <li key={i} className={`alert alert-${a.kind}`}>{a.message}</li>)}
        </ul>
      )}
    </section>
  );
}
