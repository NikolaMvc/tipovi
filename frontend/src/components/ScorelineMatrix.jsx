// Poisson 7x7 heatmap. matrix[home][away] = probability percent.
function cellColor(v, max) {
  if (max <= 0) return "transparent";
  const t = Math.min(1, v / max);
  // interpolate transparent -> neon blue
  return `rgba(0, 179, 255, ${0.06 + t * 0.85})`;
}

export default function ScorelineMatrix({ matrix }) {
  if (!matrix?.length) return <div className="text-xs text-muted">Data unavailable</div>;
  const max = Math.max(...matrix.flat());
  const n = matrix.length;

  return (
    <div className="overflow-x-auto">
      <table className="num border-separate" style={{ borderSpacing: 3 }}>
        <thead>
          <tr>
            <th className="px-1 text-[9px] text-muted">H\A</th>
            {Array.from({ length: n }).map((_, a) => (
              <th key={a} className="px-1 text-[10px] text-muted">{a}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, h) => (
            <tr key={h}>
              <td className="px-1 text-[10px] text-muted">{h}</td>
              {row.map((v, a) => (
                <td
                  key={a}
                  className="h-7 w-7 rounded text-center text-[9px] text-[#E6EDF3]"
                  style={{ backgroundColor: cellColor(v, max) }}
                  title={`${h}-${a}: ${v.toFixed(2)}%`}
                >
                  {v >= 1 ? v.toFixed(0) : ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-1 text-[10px] text-muted">Home goals (rows) × Away goals (cols), % chance</div>
    </div>
  );
}
