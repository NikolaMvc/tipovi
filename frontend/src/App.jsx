import { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
import TabNav from "./components/TabNav.jsx";
import TeamSearch from "./components/TeamSearch.jsx";
import MatchList from "./components/MatchList.jsx";
import MatchDetail from "./components/MatchDetail.jsx";
import MyTips from "./components/MyTips.jsx";
import StatsPanel from "./components/StatsPanel.jsx";

export default function App() {
  const [tab, setTab] = useState("matches");
  const [matches, setMatches] = useState([]);
  const [loadingMatches, setLoadingMatches] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);

  const [tips, setTips] = useState(null);
  const [loadingTips, setLoadingTips] = useState(false);
  const [stats, setStats] = useState(null);
  const [loadingStats, setLoadingStats] = useState(false);
  const [online, setOnline] = useState(true);

  const loadMatches = useCallback(async () => {
    setLoadingMatches(true);
    try {
      const data = await api.matches("upcoming");
      setMatches(data.matches || []);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoadingMatches(false);
    }
  }, []);

  const loadTips = useCallback(async () => {
    setLoadingTips(true);
    try {
      setTips(await api.tips());
    } catch {
      setTips({ active: [], settled: [] });
    } finally {
      setLoadingTips(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      setStats(await api.stats());
    } catch {
      setStats(null);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  useEffect(() => { loadMatches(); }, [loadMatches]);
  useEffect(() => { if (tab === "tips") loadTips(); }, [tab, loadTips]);
  useEffect(() => { if (tab === "stats") loadStats(); }, [tab, loadStats]);

  async function openMatch(id) {
    setSelectedId(id);
    setDetail(null);
    try {
      setDetail(await api.match(id));
    } catch {
      setDetail(null);
    }
  }

  async function handleAddTip(match, bet) {
    try {
      await api.addTip({
        match_id: match.id,
        market: bet.market,
        pick: bet.pick,
        odds: bet.odds,
        our_prob: bet.our_prob,
        value: bet.value,
        kelly_pct: bet.half_kelly_pct ?? bet.kelly_pct ?? 0,
      });
      // brief inline confirmation via tips reload
      if (tab === "tips") loadTips();
    } catch {
      /* swallow — graceful */
    }
  }

  async function handleDeleteTip(id) {
    await api.deleteTip(id);
    loadTips();
  }

  return (
    <div className="mx-auto min-h-screen max-w-2xl px-4 pb-16 pt-5">
      {/* Header */}
      <header className="mb-5 flex items-center justify-between">
        <h1 className="text-lg font-bold tracking-tight">
          Predict<span className="text-accent">AI</span>
        </h1>
        <span className="num flex items-center gap-1.5 text-xs text-accent">
          <span className="live-dot text-accent">●</span> {online ? "live" : "offline"}
        </span>
      </header>

      <TabNav active={tab} onChange={(t) => { setTab(t); setSelectedId(null); setDetail(null); }} />

      <div className="mt-4">
        {tab === "matches" && (
          selectedId ? (
            detail ? (
              <MatchDetail
                detail={detail}
                onBack={() => { setSelectedId(null); setDetail(null); }}
                onAddTip={handleAddTip}
              />
            ) : (
              <div className="skeleton h-64 w-full rounded-card" />
            )
          ) : (
            <div className="space-y-4">
              <TeamSearch onPredicted={(id) => { loadMatches(); openMatch(id); }} />
              <MatchList matches={matches} loading={loadingMatches} onSelect={openMatch} />
            </div>
          )
        )}

        {tab === "tips" && <MyTips tips={tips} loading={loadingTips} onDelete={handleDeleteTip} />}

        {tab === "stats" && <StatsPanel stats={stats} loading={loadingStats} />}
      </div>
    </div>
  );
}
