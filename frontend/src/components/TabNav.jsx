const TABS = [
  { id: "matches", label: "Utakmice" },
  { id: "tips", label: "Moji tipovi" },
  { id: "stats", label: "Statistika" },
];

export default function TabNav({ active, onChange }) {
  return (
    <div className="flex gap-1 rounded-card border border-hair bg-card p-1">
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            active === t.id ? "bg-[#00B3FF1a] text-accent" : "text-muted hover:text-[#E6EDF3]"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
