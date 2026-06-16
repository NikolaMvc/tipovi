const MAP = {
  HIGH: { color: "#00E5A0", label: "HIGH" },
  MEDIUM: { color: "#FFB020", label: "MEDIUM" },
  LOW: { color: "#FF4757", label: "LOW" },
};

export default function ConfidenceBadge({ confidence, score }) {
  const c = MAP[confidence] || MAP.LOW;
  return (
    <span
      className="num inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
      style={{
        color: c.color,
        backgroundColor: `${c.color}1a`,
        border: `1px solid ${c.color}4d`,
      }}
      title={score != null ? `Confidence score: ${score}` : undefined}
    >
      {c.label}
      {score != null && <span className="opacity-70">{score}</span>}
    </span>
  );
}
