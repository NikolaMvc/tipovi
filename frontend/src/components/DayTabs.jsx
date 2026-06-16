export default function DayTabs({ days = [], active, onChange, label }) {
  if (!days.length) return null;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {days.map((d) => (
        <button
          key={d}
          onClick={() => onChange(d)}
          className={`num whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
            active === d
              ? "border-[#00B3FF] bg-[#00B3FF1a] text-accent"
              : "border-hair bg-card text-muted hover:text-[#E6EDF3]"
          }`}
        >
          {label(d)}
        </button>
      ))}
    </div>
  );
}
