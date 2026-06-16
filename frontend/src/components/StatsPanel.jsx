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
  if (!stats) return <Empty>No stats available.</Empty>;

  const profitColor = stats.profit > 0 ? "#00E5A0" : stats.profit < 0 ? "#FF4757" : "#E6EDF3";
  const timeline = (stats.timeline || []).map((t, i) => ({
    i: i + 1,
    profit: t.profit,
    date: new Date(t.date).toLocaleDateString(),
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Win rate" value={`${stats.win_rate}%`} accent="#00B3FF" />
        <Metric label="Tips" value={stats.total_tips} />
        <Metric label="ROI" value={`${stats.roi}%`} accent={profitColor} />
        <Metric label="Profit (u)" value={stats.profit} accent={profitColor} />
      </div>

      <div className="rounded-card border border-hair bg-card p-4">
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">Profit over time</h3>
        {timeline.length ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={timeline} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis dataKey="i" tick={{ fill: "#5A6573", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#5A6573", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "#151B24", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#8A93A2" }}
                formatter={(v) => [`${v} u`, "cumulative"]}
              />
              <Line type="monotone" dataKey="profit" stroke="#00B3FF" strokeWidth={2} dot={false} />
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
                  {m.won}-{m.lost} · <span className="text-accent">{m.win_rate}%</span> ·{" "}
                  <span style={{ color: m.profit >= 0 ? "#00E5A0" : "#FF4757" }}>{m.profit > 0 ? "+" : ""}{m.profit}u</span>
                </span>
              </div>
            ))
          ) : <Empty>No market data yet.</Empty>}
        </div>
      </div>
    </div>
  );
}
