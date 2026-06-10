import {
  getCockpitData,
  formatEur,
  relTime,
  humanizeType,
  PALIER_1,
  PALIERS,
  type DecisionRow,
  type FeedEntry,
} from "@/lib/data";

export const revalidate = 300;

const AGENT_LABEL: Record<FeedEntry["agent"], { icon: string; name: string }> = {
  observer: { icon: "🔍", name: "Observer" },
  optimiseur: { icon: "⚡", name: "Optimiseur" },
  relanceur: { icon: "📞", name: "Relanceur" },
  stratege: { icon: "🎯", name: "Stratège" },
};

const VERDICT_ICON = { good: "✅", warn: "⚠️", bad: "🔴" } as const;

function decisionImpact(d: DecisionRow): string {
  const p = d.payload || {};
  const parts: string[] = [];
  if (p.summary) parts.push(String(p.summary));
  else if (p.current) parts.push(String(p.current));
  return parts.join(" · ") || "détail dans le journal de décisions";
}

export default async function Home() {
  const data = await getCockpitData();
  const now = new Date(data.generatedAt);

  const dateLabel = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Europe/Paris",
  }).format(now);

  const healthy = data.attentionCount === 0 && !data.error;
  const gaugePct = Math.min(100, (data.collecteAttenduMtd / PALIER_1) * 100);

  return (
    <main className="container">
      {/* 1. Header */}
      <header className="header">
        <div>
          <div className="eyebrow">Cockpit AIOS</div>
          <h1>Gigi Academy — Cockpit</h1>
          <div className="header-date">{dateLabel}</div>
        </div>
        <span className={`health-badge ${healthy ? "health-ok" : "health-warn"}`}>
          <span className="dot" />
          {healthy
            ? "Tout roule"
            : `${data.attentionCount || 1} point${data.attentionCount > 1 ? "s" : ""} d'attention`}
        </span>
      </header>

      {data.error && (
        <div className="data-error">
          Données momentanément indisponibles ({data.error}). Réessaie dans quelques minutes.
        </div>
      )}

      {/* 2. Brief du jour */}
      {data.brief.length > 0 && (
        <section className="brief">
          <div className="label">Le brief du jour</div>
          {data.brief.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </section>
      )}

      {/* 3. Jauge palier */}
      <section
        className="gauge"
        title="fact_eod_closeuse.cash_contracte (mois courant, sentinel exclu) × 0,8"
      >
        <div className="label">Palier 1 — collecté attendu ce mois-ci</div>
        <div className="score">
          <span className="big">{formatEur(data.collecteAttenduMtd)}</span>
          <span className="vs">sur {formatEur(PALIER_1)}</span>
        </div>
        <div className="bar">
          <span className="fill" style={{ width: `${gaugePct}%` }} />
        </div>
        <div className="meta">
          <span>
            <strong>{formatEur(data.contracteMtd)}</strong> contractés ce mois × 80 % collectés
            (règle d&apos;or)
          </span>
          <span>
            à ce rythme : <strong>{formatEur(data.projectionMois)}</strong> fin de mois
          </span>
        </div>
        <div className="paliers">
          {PALIERS.map((p, i) => (
            <span key={p}>
              {i > 0 && " → "}
              <span className={i === 0 ? "current" : undefined}>
                {Math.round(p / 1000)}k
              </span>
            </span>
          ))}{" "}
          €/mois
        </div>
      </section>

      {/* 4. KPI cards */}
      <div className="kpis">
        {data.kpis.map((k) => (
          <div key={k.label} className={`kpi v-${k.verdict}`} title={k.source}>
            <div className="label">
              <span>{k.label}</span>
              <span>{VERDICT_ICON[k.verdict]}</span>
            </div>
            <div className="value">{k.display}</div>
            <div className="sub">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* 5. Décisions en attente */}
      <h2>
        Décisions en attente{" "}
        <span className="count">
          {data.decisionsProposed.length > 0 ? `· ${data.decisionsProposed.length}` : ""}
        </span>
      </h2>
      {data.decisionsProposed.length === 0 ? (
        <p className="calm">Aucune décision en attente.</p>
      ) : (
        data.decisionsProposed.map((d) => (
          <article key={d.id} className="decision">
            <div className="top">
              <div className="title">{d.payload?.title || humanizeType(d.decision_type)}</div>
              <span className="badge-whatsapp">Validation via WhatsApp</span>
            </div>
            <div className="impact">
              <strong>{AGENT_LABEL[agentOf(d.agent_name)].name}</strong> · {decisionImpact(d)} ·{" "}
              {relTime(d.created_at, now)}
            </div>
          </article>
        ))
      )}

      {/* 6. Fil d'activité */}
      <h2>Fil d&apos;activité</h2>
      {data.feed.length === 0 ? (
        <p className="calm">Journée calme — rien à signaler.</p>
      ) : (
        <ul className="feed">
          {data.feed.map((e, i) => {
            const a = AGENT_LABEL[e.agent];
            return (
              <li key={i}>
                <span className={`icon ${e.agent}`}>{a.icon}</span>
                <div>
                  <div className="head">
                    <span className={`agent-name ${e.agent}`}>{a.name}</span>
                    <span className="when">{relTime(e.at, now)}</span>
                    {e.status && <span className={`status-pill ${e.status}`}>{statusFr(e.status)}</span>}
                  </div>
                  <div className="what">
                    {e.title} — <strong>{e.result}</strong>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Footer */}
      <footer className="footer">
        <span>
          Données : Supabase gigi-data-os · mise à jour auto toutes les 5 min
        </span>
        <span className="powered">
          Powered by <strong>Scale.IA</strong>
        </span>
      </footer>
    </main>
  );
}

function agentOf(name: string): FeedEntry["agent"] {
  const n = (name || "").toLowerCase();
  if (n.includes("optim")) return "optimiseur";
  if (n.includes("relan")) return "relanceur";
  if (n.includes("strat")) return "stratege";
  return "observer";
}

function statusFr(status: string): string {
  switch (status) {
    case "proposed":
      return "à valider";
    case "approved":
      return "validée";
    case "executed":
      return "exécutée";
    case "rejected":
      return "refusée";
    default:
      return status;
  }
}
