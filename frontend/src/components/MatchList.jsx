import MatchCard from "./MatchCard.jsx";
import { ListSkeleton, Empty } from "./Skeleton.jsx";

export default function MatchList({ matches, loading, onSelect }) {
  if (loading) return <ListSkeleton n={5} />;
  if (!matches?.length)
    return (
      <Empty>
        No matches for this day.
        <div className="mt-1 text-xs">Run <span className="num text-accent">python run.py</span> to refresh the snapshot.</div>
      </Empty>
    );
  return (
    <div className="space-y-3">
      {matches.map((item) => (
        <MatchCard key={item.match.id} item={item} onClick={() => onSelect(item)} />
      ))}
    </div>
  );
}
