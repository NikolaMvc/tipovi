export default function ProbabilityBar({ home = 0, draw = 0, away = 0 }) {
  const total = home + draw + away || 1;
  const h = (home / total) * 100;
  const d = (draw / total) * 100;
  const a = (away / total) * 100;

  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-[#0A0E14]">
        <div style={{ width: `${h}%`, backgroundColor: "#00B3FF" }} />
        <div style={{ width: `${d}%`, backgroundColor: "#3A4452" }} />
        <div style={{ width: `${a}%`, backgroundColor: "#FF4757" }} />
      </div>
      <div className="num mt-2 flex justify-between text-xs">
        <span style={{ color: "#00B3FF" }}>1 {home.toFixed(0)}%</span>
        <span style={{ color: "#8A93A2" }}>X {draw.toFixed(0)}%</span>
        <span style={{ color: "#FF4757" }}>2 {away.toFixed(0)}%</span>
      </div>
    </div>
  );
}
