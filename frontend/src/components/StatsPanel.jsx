import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Empty } from "./Skeleton.jsx";

function Metric({ label, value, accent }) {
  return (
    <div className="rounded-card border border-hair bg-card p-4">
      <div className="text-[10px] uppercase tracking-widest text-muted">{label}</div>
      <div className="num mt-1 text-2xl font-bold" style={{ color: accent || "#E6EDF3" }}>{value}</div>
    </div>
  );
}

export default function StatsPanel({ stats, loading }) {
  if (loading) return <div className="skeleton h-40 w-full rounded-card" />;
  if (!stats || !stats.total_tips) return <Empty>No tips to analyse yet.</Empty>;

  const profitColor = stats.profit == null ? "#E6EDF3" : stats.profit > 0 ? "#00E5A0" : stats.profit < 0 ? "#FF4757" : "#E6EDF3";
  const lineLabel = stats.has_odds ? "units" : "net hits";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Win rate" value={`${stats.win_rate}%`} accent="#00B3FF" />
        <Metric label="Settled" value={`${stats.won}/${stats.settled || 0}`} accent="#00E5A0" />
        <Metric label="ROI" value={stats.roi == null ? "—" : `${stats.roi}%`} accent={profitColor} />
        <Metric label={stats.has_odds ? "Profit (u)" : "Pending"} value={stats.has_odds ? stats.profit : stats.pending} accent={profitColor} />
      </div>

      <div className="rounded-card border border-hair bg-card p-4">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
          Performance over time
        </h3>
        {stats.timeline?.length ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={stats.timeline} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis dataKey="i" tick={{ fill: "#5A6573", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#5A6573", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "#151B24", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#8A93A2" }}
                formatter={(v) => [`${v} ${lineLabel}`, "cumulative"]}
              />
              <Line type="monotone" dataKey="value" stroke="#00B3FF" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : <Empty>Settle some tips to see the trend.</Empty>}
      </div>

      <div className="rounded-card border border-hair bg-card p-4">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">By market</h3>
        <div className="space-y-2">
          {Object.keys(stats.by_market || {}).length ? (
            Object.entries(stats.by_market).map(([market, m]) => (
              <div key={market} className="num flex items-center justify-between text-sm">
                <span className="text-[#E6EDF3]">{market}</span>
                <span className="text-muted">
                  {m.won}-{m.lost} <span className="opacity-60">/ {m.total}</span> ·{" "}
                  <span className="text-accent">{m.win_rate}%</span>
                </span>
              </div>
            ))
          ) : <Empty>No market data yet.</Empty>}
        </div>
      </div>
    </div>
  );
}
