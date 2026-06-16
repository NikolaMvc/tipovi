import { useState } from "react";
import { api } from "../api.js";

export default function TeamSearch({ onPredicted }) {
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    if (!home.trim() || !away.trim()) return;
    setLoading(true);
    setError("");
    try {
      const detail = await api.predict(home.trim(), away.trim());
      onPredicted(detail.match.id);
    } catch (e) {
      setError("Could not compute (data unavailable for this fixture).");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-card border border-hair bg-card p-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={home}
          onChange={(e) => setHome(e.target.value)}
          placeholder="Home team"
          className="flex-1 rounded-lg border border-hair bg-[#0A0E14] px-3 py-2 text-sm text-[#E6EDF3] outline-none placeholder:text-muted focus:border-[#00B3FF55]"
        />
        <input
          value={away}
          onChange={(e) => setAway(e.target.value)}
          placeholder="Away team"
          onKeyDown={(e) => e.key === "Enter" && run()}
          className="flex-1 rounded-lg border border-hair bg-[#0A0E14] px-3 py-2 text-sm text-[#E6EDF3] outline-none placeholder:text-muted focus:border-[#00B3FF55]"
        />
        <button
          onClick={run}
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#04121C] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Computing…" : "Predict"}
        </button>
      </div>
      {error && <div className="mt-2 text-[11px] text-away">{error}</div>}
    </div>
  );
}
