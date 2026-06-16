const COLORS = { W: "#00E5A0", D: "#FFB020", L: "#FF4757" };

function Dot({ r }) {
  const c = COLORS[r] || "#3A4452";
  return (
    <span
      className="num inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold"
      style={{ color: c, backgroundColor: `${c}1f`, border: `1px solid ${c}55` }}
    >
      {r}
    </span>
  );
}

export default function FormGuide({ results = [], label }) {
  return (
    <div className="flex items-center gap-2">
      {label && <span className="w-16 text-xs text-muted">{label}</span>}
      <div className="flex gap-1">
        {results.length ? (
          results.map((r, i) => <Dot key={i} r={r} />)
        ) : (
          <span className="text-xs text-muted">Data unavailable</span>
        )}
      </div>
    </div>
  );
}
