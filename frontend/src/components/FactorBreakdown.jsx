import { useState } from "react";

const LABELS = {
  form: "Forma",
  xg: "xG (proxy)",
  attack_defense: "Snaga napada/odbrane",
  home: "Domaći faktor",
  h2h: "H2H",
  fatigue: "Umor",
};
const ORDER = ["form", "xg", "attack_defense", "home", "h2h", "fatigue"];

function Contrib({ v }) {
  if (v == null) return <span className="text-muted">—</span>;
  const c = v > 0 ? "#00E5A0" : v < 0 ? "#FF4757" : "#8A93A2";
  return <span style={{ color: c }}>{v > 0 ? "+" : ""}{v.toFixed(3)}</span>;
}

function FormMatches({ matches, team }) {
  if (!matches?.length) return <div className="text-xs text-muted">Data unavailable</div>;
  return (
    <div className="mt-1">
      <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">{team}</div>
      <div className="space-y-1">
        {matches.map((m, i) => (
          <div key={i} className="num flex items-center justify-between text-[11px]">
            <span className="text-[#E6EDF3]">
              vs {m.opponent || "?"}{" "}
              <span className="text-muted">
                ({m.position}{m.position_estimated ? "~" : ""}.) · {m.venue === "home" ? "kuća" : "gost"} · {m.outcome} {m.score}
              </span>
            </span>
            <span className="font-semibold" style={{ color: m.points >= 2 ? "#00E5A0" : m.points === 1 ? "#FFB020" : "#FF4757" }}>
              {m.points} {m.points === 1 ? "bod" : "boda"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function FactorBreakdown({ detail }) {
  const [open, setOpen] = useState("form");
  const fu = detail?.breakdown?.factors_used;
  if (!fu) return null;
  const hf = fu.home_factors || {};
  const af = fu.away_factors || {};
  const b = detail.breakdown;
  const xg = b.xg || {};
  const lambda = detail.prediction?.lambda || {};

  function extra(key) {
    if (key === "form")
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormMatches matches={fu.form?.home_matches} team={`${detail.match.home_team} · ${fu.form?.home_form_score ?? "—"}/3`} />
          <FormMatches matches={fu.form?.away_matches} team={`${detail.match.away_team} · ${fu.form?.away_form_score ?? "—"}/3`} />
        </div>
      );
    if (key === "xg")
      return (
        <div className="num text-[11px] text-muted">
          xG: <span className="text-[#E6EDF3]">{xg.home_xg ?? "—"}</span> – <span className="text-[#E6EDF3]">{xg.away_xg ?? "—"}</span>
          {xg.is_proxy && <span className="ml-2 rounded bg-[#FFB02022] px-1 text-amber">PROXY ({xg.home_source}/{xg.away_source})</span>}
        </div>
      );
    if (key === "attack_defense")
      return <div className="num text-[11px] text-muted">Izvedeno iz golova datih/primljenih u zadnjih 5 (napad × slabost odbrane protivnika).</div>;
    if (key === "home")
      return <div className="num text-[11px] text-muted">Prednost domaćeg terena (fiksni faktor): domaćin ×1.20, gost ×0.85.</div>;
    if (key === "h2h" && b.h2h)
      return <div className="num text-[11px] text-muted">Međusobni: {b.h2h.home_wins}-{b.h2h.draws}-{b.h2h.away_wins} ({b.h2h.matches} mečeva), avg {b.h2h.avg_goals ?? "—"} gol.</div>;
    if (key === "fatigue" && b.fatigue)
      return <div className="num text-[11px] text-muted">Odmor: domaćin {b.fatigue.home_rest_days ?? "—"}d ({b.fatigue.home_status}), gost {b.fatigue.away_rest_days ?? "—"}d ({b.fatigue.away_status}).</div>;
    return null;
  }

  return (
    <div className="rounded-card border border-hair bg-card p-4">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">Kako je izračunato (λ breakdown)</h3>

      <div className="num mb-3 flex items-center justify-between rounded-lg border border-hair bg-[#0A0E14] px-3 py-2 text-sm">
        <span className="text-muted">Finalni λ</span>
        <span><span className="text-accent">{lambda.home}</span> <span className="text-muted">–</span> <span className="text-[#FF4757]">{lambda.away}</span></span>
      </div>

      <div className="space-y-1">
        {ORDER.filter((k) => hf[k] || af[k]).map((k) => {
          const h = hf[k] || {};
          const a = af[k] || {};
          const w = (h.weight ?? a.weight ?? 0) * 100;
          const isOpen = open === k;
          return (
            <div key={k} className="rounded-lg border border-hair bg-[#0A0E14]">
              <button onClick={() => setOpen(isOpen ? null : k)} className="flex w-full items-center justify-between px-3 py-2 text-left">
                <span className="text-sm text-[#E6EDF3]">{LABELS[k]}</span>
                <span className="num flex items-center gap-3 text-[11px]">
                  <span className="text-muted">tež. {w.toFixed(0)}%</span>
                  <span>λH <Contrib v={h.contribution} /></span>
                  <span>λA <Contrib v={a.contribution} /></span>
                  <span className="text-muted">{isOpen ? "▲" : "▼"}</span>
                </span>
              </button>
              {isOpen && <div className="border-t border-hair px-3 py-2">{extra(k)}</div>}
            </div>
          );
        })}
      </div>

      {b.positions_estimated > 0 && (
        <div className="mt-2 text-[10px] text-amber">⚠ {b.positions_estimated} pozicija protivnika nepoznata → procjena (sredina tabele).</div>
      )}
      {fu && detail.breakdown?.notes?.length > 0 && (
        <div className="mt-1 text-[10px] text-muted">{detail.breakdown.notes.join(" · ")}</div>
      )}
    </div>
  );
}
