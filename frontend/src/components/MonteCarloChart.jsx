import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

export default function MonteCarloChart({ monteCarlo }) {
  if (!monteCarlo?.histogram) return <div className="text-xs text-muted">Data unavailable</div>;
  const data = Object.entries(monteCarlo.histogram)
    .map(([goals, pct]) => ({ goals: Number(goals), pct }))
    .sort((a, b) => a.goals - b.goals);

  return (
    <div>
      <div className="num mb-2 flex items-center justify-between text-xs text-muted">
        <span>{monteCarlo.simulations?.toLocaleString()} simulations</span>
        <span>CI {monteCarlo.confidence_interval}</span>
      </div>
      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
          <XAxis dataKey="goals" tick={{ fill: "#5A6573", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#5A6573", fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(255,255,255,0.04)" }}
            contentStyle={{ background: "#151B24", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#8A93A2" }}
            formatter={(v) => [`${v}%`, "chance"]}
            labelFormatter={(l) => `${l} total goals`}
          />
          <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill="#00B3FF" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
