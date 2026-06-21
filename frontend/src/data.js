// Static data layer — reads the JSON snapshots Vercel serves from /data/.
// No backend: everything is a pre-computed file written by `python run.py`.

const BASE = import.meta.env.BASE_URL || "/";

async function getJson(path) {
  try {
    const res = await fetch(`${BASE}data/${path}?t=${Date.now()}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export const data = {
  index: () => getJson("index.json"),
  predictions: (date) => getJson(`predictions/${date}.json`),
  results: (date) => getJson(`results/${date}.json`),
  tips: (date) => getJson(`tips/${date}.json`),
};

// --- Day labels (Danas / Sutra / Prekosutra / date) ---
export function dayLabel(dateStr) {
  if (dateStr === "ukupno") return "Ukupno";
  const today = new Date();
  const t = new Date(dateStr + "T00:00:00");
  const diff = Math.round((t - new Date(today.toDateString())) / 86400000);
  if (diff === 0) return "Danas";
  if (diff === 1) return "Sutra";
  if (diff === 2) return "Prekosutra";
  if (diff === -1) return "Juče";
  if (diff === -2) return "Prekjuče";
  return t.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

// today's date as YYYY-MM-DD (local)
export function todayStr() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

export function dayOffset(dateStr) {
  const today = new Date();
  const t = new Date(dateStr + "T00:00:00");
  return Math.round((t - new Date(today.toDateString())) / 86400000);
}

// --- Client-side stats from merged tips (auto top-N) ---
export function computeStats(tips) {
  const won = tips.filter((t) => t.status === "WON");
  const lost = tips.filter((t) => t.status === "LOST");
  const pending = tips.filter((t) => t.status === "PENDING");
  const settled = won.length + lost.length;

  const hasOdds = tips.some((t) => t.odds);
  const profit = hasOdds
    ? won.reduce((s, t) => s + ((t.odds || 0) - 1), 0) - lost.length
    : null;

  const byMarket = {};
  for (const t of tips) {
    const m = (byMarket[t.market] ||= { total: 0, won: 0, lost: 0 });
    m.total += 1;
    if (t.status === "WON") m.won += 1;
    else if (t.status === "LOST") m.lost += 1;
  }
  for (const m of Object.values(byMarket)) {
    const s = m.won + m.lost;
    m.win_rate = s ? Math.round((m.won / s) * 100) : 0;
  }

  // cumulative timeline over settled tips (chronological by date)
  let cum = 0;
  const timeline = tips
    .filter((t) => t.status !== "PENDING" && t.date)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .map((t, i) => {
      if (hasOdds) cum += t.status === "WON" ? (t.odds || 0) - 1 : -1;
      else cum += t.status === "WON" ? 1 : 0;
      return { i: i + 1, value: Math.round(cum * 100) / 100 };
    });

  return {
    total_tips: tips.length,
    won: won.length,
    lost: lost.length,
    pending: pending.length,
    settled,
    win_rate: settled ? Math.round((won.length / settled) * 100) : 0,
    roi: hasOdds && settled ? Math.round((profit / settled) * 1000) / 10 : null,
    profit: hasOdds ? Math.round(profit * 100) / 100 : null,
    has_odds: hasOdds,
    by_market: byMarket,
    timeline,
  };
}
