export default function H2HTimeline({ h2h, homeTeam, awayTeam }) {
  if (!h2h || !h2h.matches) return <div className="text-xs text-muted">Data unavailable</div>;
  const total = h2h.matches || 1;
  const hw = (h2h.home_wins / total) * 100;
  const dw = (h2h.draws / total) * 100;
  const aw = (h2h.away_wins / total) * 100;
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-[#0A0E14]">
        <div style={{ width: `${hw}%`, backgroundColor: "#00B3FF" }} />
        <div style={{ width: `${dw}%`, backgroundColor: "#3A4452" }} />
        <div style={{ width: `${aw}%`, backgroundColor: "#FF4757" }} />
      </div>
      <div className="num mt-2 flex justify-between text-xs">
        <span style={{ color: "#00B3FF" }}>{homeTeam} {h2h.home_wins}</span>
        <span className="text-muted">Draws {h2h.draws}</span>
        <span style={{ color: "#FF4757" }}>{h2h.away_wins} {awayTeam}</span>
      </div>
      {h2h.avg_goals != null && (
        <div className="num mt-2 text-[11px] text-muted">
          Avg goals/match: <span className="text-[#E6EDF3]">{h2h.avg_goals}</span> · {h2h.matches} meetings
        </div>
      )}
    </div>
  );
}
