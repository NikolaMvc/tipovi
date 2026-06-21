import { ListSkeleton, Empty } from "./Skeleton.jsx";

const STATUS = {
  WON: { c: "#00E5A0", icon: "✓" },
  LOST: { c: "#FF4757", icon: "✕" },
  PENDING: { c: "#FFB020", icon: "•" },
};

function fmtDT(s) {
  if (!s) return "";
  try {
    const d = new Date(s);
    return d.toLocaleString(undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function TipRow({ tip, rank, onSelect }) {
  const s = STATUS[tip.status] || STATUS.PENDING;
  return (
    <button
      onClick={() => onSelect?.(tip)}
      className="flex w-full items-center justify-between rounded-card border bg-card p-3 text-left transition-colors hover:border-[#00B3FF55]"
      style={{ borderColor: `${s.c}4d`, backgroundColor: `${s.c}0d` }}
    >
      <div className="flex min-w-0 items-center gap-3">
        {rank != null && <span className="num w-5 text-center text-xs text-muted">{rank}</span>}
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[#E6EDF3]">
            {tip.home_team} <span className="text-muted">v</span> {tip.away_team}
          </div>
          <div className="num mt-0.5 text-[11px] text-muted">
            <span className="text-[#8A93A2]">{fmtDT(tip.date)}</span> · {tip.market} ·{" "}
            <span className="text-[#E6EDF3]">{tip.pick}</span>
            {tip.odds ? <span className="ml-1 text-accent">@ {tip.odds}</span> : null}
            {tip.final_score ? <span className="ml-1 opacity-70">({tip.final_score})</span> : null}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="num text-sm font-bold text-accent">{tip.probability}%</span>
        <span className="num text-sm font-bold" style={{ color: s.c }}>{s.icon}</span>
      </div>
    </button>
  );
}

export default function MyTips({ tips, loading, onSelect }) {
  if (loading) return <ListSkeleton n={5} />;
  if (!tips || !tips.length)
    return <Empty>No tips yet. Run <span className="num text-accent">python run.py</span> to generate the day's top picks.</Empty>;

  const active = tips.filter((t) => t.status === "PENDING").sort((a, b) => b.probability - a.probability);
  const settled = tips.filter((t) => t.status !== "PENDING").sort((a, b) => b.probability - a.probability);

  return (
    <div className="space-y-6">
      <div className="text-[11px] text-muted">
        Top-20 tipova po najvećoj vjerovatnoći za 1 / X / 2. Klikni tip za pun detalj (O/U, BTTS, breakdown).
      </div>
      <div>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">Aktivni</h3>
        <div className="space-y-2">
          {active.length ? active.map((t, i) => <TipRow key={`${t.match_id}-a${i}`} tip={t} rank={i + 1} onSelect={onSelect} />)
            : <Empty>No pending tips.</Empty>}
        </div>
      </div>
      <div>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">Riješeni</h3>
        <div className="space-y-2">
          {settled.length ? settled.map((t, i) => <TipRow key={`${t.match_id}-s${i}`} tip={t} onSelect={onSelect} />)
            : <Empty>No settled tips yet.</Empty>}
        </div>
      </div>
    </div>
  );
}
