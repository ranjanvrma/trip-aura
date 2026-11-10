export function Skeleton({ w = "100%", h = 14, r }: { w?: number | string; h?: number; r?: number }) {
  return <span className="skeleton" style={{ width: w, height: h, borderRadius: r }} aria-hidden />;
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div className="stack-s" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} w={i === lines - 1 ? "60%" : "100%"} />)}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}
