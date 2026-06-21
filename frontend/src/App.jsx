import { useEffect, useState, useCallback } from "react";
import { data, dayLabel, computeStats, todayStr, dayOffset } from "./data.js";
import TabNav from "./components/TabNav.jsx";
import DayTabs from "./components/DayTabs.jsx";
import MatchList from "./components/MatchList.jsx";
import MatchDetail from "./components/MatchDetail.jsx";
import MyTips from "./components/MyTips.jsx";
import StatsPanel from "./components/StatsPanel.jsx";
import { Empty } from "./components/Skeleton.jsx";

export default function App() {
  const [tab, setTab] = useState("matches");
  const [index, setIndex] = useState(null);
  const [online, setOnline] = useState(true);

  const [day, setDay] = useState(null);
  const [matches, setMatches] = useState([]);
  const [loadingMatches, setLoadingMatches] = useState(true);
  const [detail, setDetail] = useState(null);

  const [tips, setTips] = useState(null);
  const [loadingTips, setLoadingTips] = useState(false);
  const [stats, setStats] = useState(null);
  const [tipScope, setTipScope] = useState("ukupno");  // "ukupno" or a day string

  // Load index once.
  useEffect(() => {
    (async () => {
      const idx = await data.index();
      if (!idx) { setOnline(false); setLoadingMatches(false); return; }
      setIndex(idx);
      // Matches: default to first upcoming day (today onwards).
      const up = (idx.prediction_days || []).filter((d) => d >= todayStr());
      setDay(up[0] || null);
    })();
  }, []);

  // Load matches for the selected day.
  const loadMatches = useCallback(async (d) => {
    if (!d) { setMatches([]); setLoadingMatches(false); return; }
    setLoadingMatches(true);
    const p = await data.predictions(d);
    setMatches(p?.matches || []);
    setLoadingMatches(false);
  }, []);

  useEffect(() => { if (day) loadMatches(day); }, [day, loadMatches]);

  const loadTips = useCallback(async () => {
    if (!index) return;
    setLoadingTips(true);
    // "ukupno" = best 20 across the upcoming days (today + next 2); a specific day
    // (incl. past) = that day's 20 tips exactly (so settled colours stay).
    const upcoming = (index.tip_days || []).filter((d) => d >= todayStr());
    const sources = tipScope === "ukupno" ? upcoming : [tipScope];
    const all = [];
    for (const d of sources) {
      const t = await data.tips(d);
      if (t?.tips) all.push(...t.tips);
    }
    const top20 = [...all].sort((a, b) => b.probability - a.probability).slice(0, 20);
    setTips(top20);
    setStats(computeStats(top20));
    setLoadingTips(false);
  }, [index, tipScope]);

  useEffect(() => { if ((tab === "tips" || tab === "stats") && index) loadTips(); }, [tab, index, loadTips]);

  // Open the full match detail for a tip (loads that day's prediction).
  async function openTipDetail(tip) {
    const day = (tip.date || "").slice(0, 10);
    const p = await data.predictions(day);
    const match = p?.matches?.find((m) => String(m.match.id) === String(tip.match_id));
    if (match) setDetail(match);
  }

  return (
    <div className="mx-auto min-h-screen max-w-2xl px-4 pb-16 pt-5">
      <header className="mb-5 flex items-center justify-between">
        <h1 className="text-lg font-bold tracking-tight">
          Predict<span className="text-accent">AI</span>
        </h1>
        <span className="num flex items-center gap-1.5 text-xs text-accent">
          <span className="live-dot text-accent">●</span> {online ? "live" : "offline"}
        </span>
      </header>

      <TabNav active={tab} onChange={(t) => { setTab(t); setDetail(null); }} />

      <div className="mt-4">
        {detail ? (
          <MatchDetail detail={detail} onBack={() => setDetail(null)} />
        ) : (
          <>
            {tab === "matches" && (
              <div className="space-y-4">
                <DayTabs
                  days={(index?.prediction_days || []).filter((d) => d >= todayStr())}
                  active={day}
                  onChange={(d) => setDay(d)}
                  label={dayLabel}
                />
                {!online ? (
                  <Empty>
                    No data yet. Run <span className="num text-accent">python run.py</span> to
                    generate predictions, then refresh.
                  </Empty>
                ) : (
                  <MatchList matches={matches} loading={loadingMatches} onSelect={(m) => setDetail(m)} />
                )}
              </div>
            )}

            {tab === "tips" && (
              <div className="space-y-4">
                <DayTabs
                  days={[
                    ...(index?.tip_days || []).filter((d) => dayOffset(d) >= -2 && dayOffset(d) <= 2),
                    "ukupno",
                  ]}
                  active={tipScope}
                  onChange={(d) => setTipScope(d)}
                  label={(d) => (d === "ukupno" ? "Ukupno" : dayLabel(d))}
                />
                <MyTips tips={tips} loading={loadingTips} onSelect={openTipDetail} />
              </div>
            )}

            {tab === "stats" && <StatsPanel stats={stats} loading={loadingTips} />}
          </>
        )}
      </div>

      {index?.last_run && (
        <div className="mt-8 text-center text-[10px] text-muted">
          Last update: <span className="num">{new Date(index.last_run).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
