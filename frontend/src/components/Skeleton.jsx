export function MatchCardSkeleton() {
  return (
    <div className="rounded-card border border-hair bg-card p-4">
      <div className="skeleton mb-3 h-3 w-1/3 rounded" />
      <div className="skeleton mb-4 h-5 w-2/3 rounded" />
      <div className="skeleton h-2 w-full rounded-full" />
    </div>
  );
}

export function ListSkeleton({ n = 4 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: n }).map((_, i) => (
        <MatchCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="py-10 text-center text-sm text-muted">{children}</div>;
}
