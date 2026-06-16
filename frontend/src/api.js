const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text}`);
  }
  return res.json();
}

export const api = {
  matches: (status = "upcoming") => req(`/api/matches?status=${status}`),
  match: (id) => req(`/api/match/${id}`),
  predict: (home_team, away_team, league = "") =>
    req(`/api/predict`, { method: "POST", body: JSON.stringify({ home_team, away_team, league }) }),
  searchTeam: (q) => req(`/api/search/team?q=${encodeURIComponent(q)}`),
  tips: () => req(`/api/tips`),
  addTip: (tip) => req(`/api/tips`, { method: "POST", body: JSON.stringify(tip) }),
  deleteTip: (id) => req(`/api/tips/${id}`, { method: "DELETE" }),
  stats: () => req(`/api/stats`),
  health: () => req(`/api/health`),
};
