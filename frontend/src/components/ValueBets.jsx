const RATING = {
  STRONG_VALUE: { c: "#00E5A0", label: "STRONG" },
  GOOD_VALUE: { c: "#00B3FF", label: "GOOD" },
  SLIGHT_VALUE: { c: "#FFB020", label: "SLIGHT" },
};

export default function ValueBets({ bets = [] }) {
  if (!bets.length)
    return <div className="text-xs text-muted">No positive-value bets (or odds unavailable).</div>;
  return (
    <div className="space-y-2">
      {bets.map((b, i) => {
        const r = RATING[b.rating] || RATING.SLIGHT_VALUE;
        return (
          <div key={i} className="flex items-center justify-between rounded-lg border border-hair bg-[#0A0E14] px-3 py-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-[#E6EDF3]">{b.pick}</span>
                <span className="num text-[10px] text-muted">{b.market}</span>
                <span
                  className="num rounded px-1.5 py-0.5 text-[9px] font-bold"
                  style={{ color: r.c, backgroundColor: `${r.c}1a` }}
                >
                  {r.label} +{b.value}%
                </span>
              </div>
              <div className="num mt-0.5 text-[11px] text-muted">
                our {b.our_prob}% · impl {b.implied_prob}% · ½Kelly {b.half_kelly_pct}%
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="num text-sm font-semibold text-accent">{b.odds}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
