function Side({ team, missing }) {
  return (
    <div className="flex-1">
      <div className="mb-1 text-xs font-semibold text-[#E6EDF3]">{team}</div>
      {missing?.length ? (
        <ul className="space-y-1">
          {missing.map((p, i) => (
            <li key={i} className="text-[11px] text-muted">
              <span className="text-away">●</span> {p.name || p}
              {p.reason && <span className="opacity-70"> — {p.reason}</span>}
              {p.key && <span className="ml-1 text-amber">★</span>}
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-[11px] text-win">Full squad available</div>
      )}
    </div>
  );
}

export default function InjuryReport({ injuries, homeTeam, awayTeam }) {
  if (!injuries) return <div className="text-xs text-muted">Data unavailable</div>;
  return (
    <div className="flex gap-4">
      <Side team={homeTeam} missing={injuries.home_missing} />
      <Side team={awayTeam} missing={injuries.away_missing} />
    </div>
  );
}
