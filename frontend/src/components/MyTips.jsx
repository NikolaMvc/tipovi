import { ListSkeleton, Empty } from "./Skeleton.jsx";

const STATUS = {
  WON: { c: "#00E5A0", icon: "✓" },
  LOST: { c: "#FF4757", icon: "✕" },
  PENDING: { c: "#FFB020", icon: "•" },
};

function TipPill({ tip, onDelete }) {
  const s = STATUS[tip.status] || STATUS.PENDING;
  return (
    <div
      className="flex items-center justify-between rounded-card border bg-card p-3"
      style={{ borderColor: `${s.c}4d`, backgroundColor: `${s.c}0d` }}
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-[#E6EDF3]">
          {tip.home_team} <span className="text-muted">v</span> {tip.away_team}
        </div>
        <div className="num mt-0.5 text-[11px] text-muted">
          {tip.market} · <span className="text-[#E6EDF3]">{tip.pick}</span> @ {tip.odds}
          {tip.value ? <span className="ml-1 text-accent">+{tip.value}%</span> : null}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="num text-sm font-bold" style={{ color: s.c }}>{s.icon} {tip.status}</span>
        <button onClick={() => onDelete(tip.id)} className="text-xs text-muted hover:text-away">✕</button>
      </div>
    </div>
  );
}

export default function MyTips({ tips, loading, onDelete }) {
  if (loading) return <ListSkeleton n={3} />;
  if (!tips || (!tips.active.length && !tips.settled.length))
    return <Empty>No tips yet. Add value bets from a match's detail view.</Empty>;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">Active</h3>
        <div className="space-y-2">
          {tips.active.length ? tips.active.map((t) => (
            <TipPill key={t.id} tip={t} onDelete={onDelete} />
          )) : <Empty>No pending tips.</Empty>}
        </div>
      </div>
      <div>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">Settled</h3>
        <div className="space-y-2">
          {tips.settled.length ? tips.settled.map((t) => (
            <TipPill key={t.id} tip={t} onDelete={onDelete} />
          )) : <Empty>No settled tips yet.</Empty>}
        </div>
      </div>
    </div>
  );
}
