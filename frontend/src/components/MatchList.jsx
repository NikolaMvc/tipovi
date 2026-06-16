import MatchCard from "./MatchCard.jsx";
import { ListSkeleton, Empty } from "./Skeleton.jsx";

export default function MatchList({ matches, loading, onSelect }) {
  if (loading) return <ListSkeleton n={5} />;
  if (!matches?.length)
    return (
      <Empty>
        No upcoming matches in the database yet.
        <div className="mt-1 text-xs">
          The worker populates this every 6h — or search a fixture above to compute one on demand.
        </div>
      </Empty>
    );
  return (
    <div className="space-y-3">
      {matches.map((item) => (
        <MatchCard key={item.match.id} item={item} onClick={() => onSelect(item.match.id)} />
      ))}
    </div>
  );
}
