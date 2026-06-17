import MatchCard from "./MatchCard.jsx";
import { ListSkeleton, Empty } from "./Skeleton.jsx";

const CONF_RANK = { HIGH: 3, MEDIUM: 2, LOW: 1 };

// Group by league, sort leagues by their strongest prediction (major/rich leagues
// and higher confidence float to the top), and matches within a league likewise.
function groupByLeague(matches) {
  const groups = {};
  for (const m of matches) {
    const lg = m.match?.league || "Other";
    (groups[lg] ||= []).push(m);
  }
  const score = (m) =>
    (CONF_RANK[m.prediction?.confidence] || 0) * 100 + (m.prediction?.confidence_score || 0);
  const arr = Object.entries(groups).map(([league, items]) => {
    items.sort((a, b) => score(b) - score(a));
    return { league, items, top: score(items[0]) };
  });
  arr.sort((a, b) => b.top - a.top || b.items.length - a.items.length);
  return arr;
}

export default function MatchList({ matches, loading, onSelect }) {
  if (loading) return <ListSkeleton n={5} />;
  if (!matches?.length)
    return (
      <Empty>
        No matches for this day.
        <div className="mt-1 text-xs">Run <span className="num text-accent">python run.py</span> to refresh the snapshot.</div>
      </Empty>
    );

  const groups = groupByLeague(matches);

  return (
    <div className="space-y-6">
      <div className="num text-[11px] text-muted">{matches.length} matches · {groups.length} leagues</div>
      {groups.map((g) => (
        <div key={g.league}>
          <h3 className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-widest text-muted">
            <span>{g.league}</span>
            <span className="num opacity-60">{g.items.length}</span>
          </h3>
          <div className="space-y-3">
            {g.items.map((item) => (
              <MatchCard key={item.match.id} item={item} onClick={() => onSelect(item)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
