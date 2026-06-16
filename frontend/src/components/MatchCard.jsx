import ConfidenceBadge from "./ConfidenceBadge.jsx";
import ProbabilityBar from "./ProbabilityBar.jsx";

function fmtKickoff(dateStr) {
  if (!dateStr) return "TBD";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString(undefined, {
      weekday: "short", day: "numeric", month: "short",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export default function MatchCard({ item, onClick }) {
  const m = item.match;
  const p = item.prediction;
  return (
    <button
      onClick={onClick}
      className="w-full rounded-card border border-hair bg-card p-4 text-left transition-colors hover:border-[#00B3FF55]"
    >
      <div className="mb-3 flex items-start justify-between">
        <div className="text-[10px] uppercase tracking-widest text-muted">
          {m.league || "—"} · <span className="num">{fmtKickoff(m.date)}</span>
        </div>
        {p && <ConfidenceBadge confidence={p.confidence} score={p.confidence_score} />}
      </div>

      <div className="mb-4 flex items-center justify-between gap-2">
        <span className="flex-1 text-sm font-semibold text-[#E6EDF3]">{m.home_team}</span>
        <span className="text-[10px] text-muted">vs</span>
        <span className="flex-1 text-right text-sm font-semibold text-[#E6EDF3]">{m.away_team}</span>
      </div>

      {p ? (
        <ProbabilityBar home={p.home_win_prob} draw={p.draw_prob} away={p.away_win_prob} />
      ) : (
        <div className="text-xs text-muted">Prediction pending…</div>
      )}
    </button>
  );
}
