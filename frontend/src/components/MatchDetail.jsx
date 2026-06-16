import ConfidenceBadge from "./ConfidenceBadge.jsx";
import ProbabilityBar from "./ProbabilityBar.jsx";
import ScorelineMatrix from "./ScorelineMatrix.jsx";
import MonteCarloChart from "./MonteCarloChart.jsx";
import FormGuide from "./FormGuide.jsx";
import H2HTimeline from "./H2HTimeline.jsx";
import ValueBets from "./ValueBets.jsx";
import InjuryReport from "./InjuryReport.jsx";

function Section({ title, children, right }) {
  return (
    <div className="rounded-card border border-hair bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-widest text-muted">{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

const OUTCOME_LABEL = { HOME_WIN: "Home Win", DRAW: "Draw", AWAY_WIN: "Away Win" };

export default function MatchDetail({ detail, onBack }) {
  const m = detail.match;
  const p = detail.prediction;
  const b = detail.breakdown || {};

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-xs text-accent hover:underline">← Back to matches</button>

      {/* Header */}
      <div className="rounded-card border border-hair bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-widest text-muted">{m.league}</span>
          {p && <ConfidenceBadge confidence={p.confidence} score={p.confidence_score} />}
        </div>
        <div className="mb-1 flex items-center justify-between gap-3">
          <span className="flex-1 text-base font-bold text-[#E6EDF3]">{m.home_team}</span>
          <span className="text-xs text-muted">vs</span>
          <span className="flex-1 text-right text-base font-bold text-[#E6EDF3]">{m.away_team}</span>
        </div>
        {m.venue && <div className="mb-3 text-center text-[11px] text-muted">{m.venue}</div>}
        {p && <ProbabilityBar home={p.home_win_prob} draw={p.draw_prob} away={p.away_win_prob} />}
        {p && (
          <div className="num mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[11px] text-muted">
            <span>Pick: <span className="font-semibold text-accent">{OUTCOME_LABEL[p.predicted_outcome]}</span></span>
            <span>λ {p.lambda?.home} – {p.lambda?.away}</span>
            <span>xGoals {p.predicted_goals?.home} – {p.predicted_goals?.away}</span>
          </div>
        )}
        {p?.missing_data?.length > 0 && (
          <div className="mt-2 text-center text-[10px] text-amber">
            Missing data lowering confidence: {p.missing_data.join(", ")}
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Most Likely Scores">
          <div className="flex flex-wrap gap-2">
            {(p?.most_likely_scores || []).map((s, i) => (
              <span key={i} className="num rounded-lg border border-hair bg-[#0A0E14] px-2.5 py-1.5 text-sm">
                <span className="font-semibold text-[#E6EDF3]">{s.score}</span>
                <span className="ml-1 text-[11px] text-muted">{s.prob}%</span>
              </span>
            ))}
          </div>
        </Section>

        <Section title="Markets">
          <div className="num space-y-2 text-sm">
            <Row label="Over 2.5" a={detail.markets?.over_under_2_5?.over} b={detail.markets?.over_under_2_5?.under} la="O" lb="U" />
            <Row label="BTTS" a={detail.markets?.btts?.yes} b={detail.markets?.btts?.no} la="Yes" lb="No" />
          </div>
        </Section>

        <Section title="Poisson Scoreline Matrix">
          <ScorelineMatrix matrix={detail.poisson_matrix} />
        </Section>

        <Section title="Monte Carlo Distribution">
          <MonteCarloChart monteCarlo={p?.monte_carlo} />
        </Section>

        <Section title="Form (last 5)">
          <div className="space-y-2">
            <FormGuide label={m.home_team} results={b.form?.home_last5} />
            <FormGuide label={m.away_team} results={b.form?.away_last5} />
          </div>
        </Section>

        <Section title="Head to Head">
          <H2HTimeline h2h={b.h2h} homeTeam={m.home_team} awayTeam={m.away_team} />
        </Section>

        <Section title="Value Bets">
          <ValueBets bets={detail.value_bets} />
        </Section>

        <Section title="Injuries / Missing">
          <InjuryReport injuries={b.injuries} homeTeam={m.home_team} awayTeam={m.away_team} />
        </Section>

        <Section title="Referee">
          {b.referee ? (
            <div className="num text-xs text-muted">
              <div className="text-sm text-[#E6EDF3]">{b.referee.name || "—"}</div>
              <div className="mt-1">Avg cards {b.referee.avg_cards ?? "—"} · Avg pens {b.referee.avg_penalties ?? "—"}</div>
            </div>
          ) : <div className="text-xs text-muted">Data unavailable</div>}
        </Section>

        <Section title="Weather">
          {b.weather ? (
            <div className="num text-xs text-muted">
              <span className="text-sm text-[#E6EDF3]">{b.weather.temp ?? "—"}°C</span> · {b.weather.conditions || "—"}
              {b.weather.gol_suppressing && <span className="ml-2 text-amber">goal-suppressing</span>}
            </div>
          ) : <div className="text-xs text-muted">Data unavailable</div>}
        </Section>

        <Section title="xG / Standings">
          <div className="num space-y-1 text-xs text-muted">
            <div>xG: <span className="text-[#E6EDF3]">{b.xg?.home_xg ?? "—"}</span> – <span className="text-[#E6EDF3]">{b.xg?.away_xg ?? "—"}</span></div>
            <div>Pos: <span className="text-[#E6EDF3]">{b.standings?.home_pos ?? "—"}</span> – <span className="text-[#E6EDF3]">{b.standings?.away_pos ?? "—"}</span></div>
          </div>
        </Section>

        <Section title="Fatigue">
          {b.fatigue ? (
            <div className="num text-xs text-muted">
              <div>{m.home_team}: <span className="text-[#E6EDF3]">{b.fatigue.home_status}</span> ({b.fatigue.home_rest_days ?? "—"}d rest)</div>
              <div>{m.away_team}: <span className="text-[#E6EDF3]">{b.fatigue.away_status}</span> ({b.fatigue.away_rest_days ?? "—"}d rest)</div>
            </div>
          ) : <div className="text-xs text-muted">Data unavailable</div>}
        </Section>
      </div>

      <div className="text-center text-[10px] text-muted">
        Sources: {(detail.data_sources || []).join(", ") || "—"} · computed {detail.computed_at ? new Date(detail.computed_at).toLocaleString() : "—"}
      </div>
    </div>
  );
}

function Row({ label, a, b, la, lb }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-hair bg-[#0A0E14] px-3 py-2">
      <span className="text-muted">{label}</span>
      <span>
        <span className="text-accent">{la} {a ?? "—"}%</span>
        <span className="mx-2 text-muted">/</span>
        <span className="text-[#E6EDF3]">{lb} {b ?? "—"}%</span>
      </span>
    </div>
  );
}
