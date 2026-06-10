import {
  getCockpitData,
  formatEur,
  relTime,
  relHoursLabel,
  humanizeType,
  PALIER_1,
  PALIERS,
  PIPELINES_COUNT,
  SIGNALS_COUNT,
  type DecisionRow,
  type FeedEntry,
  type Verdict,
} from "@/lib/data";
import { isOperator } from "@/lib/op";
import { decideAction } from "./actions";

// cookies() (mode opérateur) rend la page dynamique ; les fetchs data gardent
// leur cache court (revalidate 300 dans lib/sql.ts) pour le public.
export const revalidate = 300;

/* --- Vocabulaire de santé unique (pattern Matt Gray : ON TRACK / BEHIND / OFF TRACK) --- */
const STATUS_FR: Record<Verdict, string> = {
  good: "En piste",
  warn: "En retard",
  bad: "Hors piste",
};

function StatusPill({ v }: { v: Verdict }) {
  return <span className={`pill pill-${v}`}>{STATUS_FR[v]}</span>;
}

const AGENT_NAME: Record<FeedEntry["agent"], string> = {
  observer: "Observer",
  optimiseur: "Optimiseur",
  relanceur: "Relanceur",
  stratege: "Stratège",
};

/* --- Roster d'agents (pattern Claude Claw agents-grid) --- */
type AgentKey = FeedEntry["agent"] | "salescoach";

const AGENTS: Array<{ key: AgentKey; name: string; role: string; active: boolean }> = [
  { key: "observer", name: "Observer", role: "Surveille les pipelines et la fraîcheur des données", active: true },
  { key: "optimiseur", name: "Optimiseur", role: "Traque les ads qui dépensent sans vendre", active: true },
  { key: "relanceur", name: "Relanceur", role: "Relance les leads chauds non bookés", active: false },
  { key: "salescoach", name: "Sales Coach", role: "Débriefe les calls et coache les closeuses", active: false },
  { key: "stratege", name: "Stratège", role: "Calcule le gap vers le palier et le levier n°1", active: false },
];

function decisionImpact(d: DecisionRow): string {
  const p = d.payload || {};
  if (p.summary) return String(p.summary);
  if (p.current) return String(p.current);
  return "détail dans le journal de décisions";
}

/* --- Ring SVG de progression (pattern Matt Gray command-center) --- */
function Ring({ pct }: { pct: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const filled = Math.min(100, Math.max(0, pct));
  return (
    <div className="ring" role="img" aria-label={`${Math.round(pct)} % du palier 1`}>
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} className="ring-bg" />
        <circle
          cx="60"
          cy="60"
          r={r}
          className="ring-fill"
          strokeDasharray={`${(filled / 100) * c} ${c}`}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="ring-center">
        <span className="ring-pct">
          {Math.round(pct)}
          <small>%</small>
        </span>
        <span className="ring-sub">du palier 1</span>
      </div>
    </div>
  );
}

export default async function Home() {
  const operator = await isOperator();
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
  const gaugePct = (data.collecteAttenduMtd / PALIER_1) * 100;
  const projPct = Math.min(100, (data.projectionMois / PALIER_1) * 100);
  const gaugeVerdict: Verdict =
    data.projectionMois >= PALIER_1 ? "good" : data.projectionMois >= PALIER_1 * 0.7 ? "warn" : "bad";

  const staleHours = data.freshestPull
    ? (now.getTime() - new Date(data.freshestPull).getTime()) / 3_600_000
    : Infinity;

  // Dernière action par agent (decision_log + pulled_at pour l'Observer)
  const lastAction = (key: AgentKey): { text: string; when: string } | null => {
    if (key === "observer" && data.freshestPull) {
      return {
        text: `Données synchronisées (${PIPELINES_COUNT} pipelines)`,
        when: relTime(data.freshestPull, now),
      };
    }
    const d = data.decisionsRecent.find((row) => agentOf(row.agent_name) === key);
    if (!d) return null;
    return {
      text: d.payload?.title || humanizeType(d.decision_type),
      when: relTime(d.created_at, now),
    };
  };

  return (
    <main className="container">
      {/* 1. Header */}
      <header className="header">
        <div>
          <div className="eyebrow">Cockpit AIOS</div>
          <h1>Gigi Academy</h1>
          <div className="header-date">
            {dateLabel}
            {operator && <span className="badge-op">mode opérateur</span>}
          </div>
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

      {/* 3. Jauge palier — ring + barre + projection fantôme + cascade 30k → 60k → 100k */}
      <section
        className="gauge"
        title="fact_eod_closeuse.cash_contracte (mois courant, sentinel exclu) × 0,8"
      >
        <div className="gauge-top">
          <div className="label">Palier 1 — collecté attendu ce mois-ci</div>
          <StatusPill v={gaugeVerdict} />
        </div>
        <div className="gauge-body">
          <Ring pct={gaugePct} />
          <div className="gauge-main">
            <div className="score">
              <span className="big">{formatEur(data.collecteAttenduMtd)}</span>
              <span className="vs">sur {formatEur(PALIER_1)}</span>
            </div>
            <div className="bar">
              <span className="ghost" style={{ width: `${projPct}%` }} />
              <span className="fill" style={{ width: `${Math.min(100, gaugePct)}%` }} />
              <span className="marker" style={{ left: `${projPct}%` }} />
            </div>
            <div className="meta">
              <span>
                <strong>{formatEur(data.contracteMtd)}</strong> contractés × 80 % collectés (règle
                d&apos;or)
              </span>
              <span>
                <span className="marker-key" /> projection fin de mois :{" "}
                <strong>{formatEur(data.projectionMois)}</strong>
              </span>
            </div>
          </div>
        </div>
        <div className="paliers">
          {PALIERS.map((p, i) => {
            const lo = i === 0 ? 0 : PALIERS[i - 1];
            const segPct = Math.min(
              100,
              Math.max(0, ((data.collecteAttenduMtd - lo) / (p - lo)) * 100)
            );
            const isCurrent = data.collecteAttenduMtd < p && (i === 0 || data.collecteAttenduMtd >= lo);
            return (
              <div key={p} className={`palier-step${isCurrent ? " current" : ""}`}>
                <div className="palier-label">
                  Palier {i + 1} · {Math.round(p / 1000)}k
                </div>
                <div className="palier-bar">
                  <span style={{ width: `${segPct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 4. KPI cards */}
      <div className="kpis">
        {data.kpis.map((k) => (
          <div key={k.label} className="kpi" title={k.source}>
            <div className="label">
              <span>{k.label}</span>
              <StatusPill v={k.verdict} />
            </div>
            <div className="value">{k.display}</div>
            <div className="sub">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* 5. Décisions en attente */}
      <h2>
        Décisions en attente
        {data.decisionsProposed.length > 0 && (
          <span className="count">{data.decisionsProposed.length}</span>
        )}
      </h2>
      {data.decisionsProposed.length === 0 ? (
        <div className="empty">
          <span className="empty-dot" />
          Rien à valider — le système tourne.
        </div>
      ) : (
        data.decisionsProposed.map((d) => (
          <article key={d.id} className="decision">
            <div className="top">
              <div className="title">{d.payload?.title || humanizeType(d.decision_type)}</div>
              {!operator && <span className="badge-whatsapp">À valider · WhatsApp</span>}
            </div>
            <div className="impact">
              <strong className={`agent-ink ${agentOf(d.agent_name)}`}>
                {AGENT_NAME[agentOf(d.agent_name)]}
              </strong>{" "}
              · {decisionImpact(d)} · {relTime(d.created_at, now)}
            </div>
            {operator && (
              <div className="op-actions">
                <form action={decideAction}>
                  <input type="hidden" name="id" value={d.id} />
                  <input type="hidden" name="action" value="approve" />
                  <button type="submit" className="btn-approve">
                    Valider
                  </button>
                </form>
                <details className="reject">
                  <summary className="btn-reject">Refuser</summary>
                  <form action={decideAction} className="reject-box">
                    <input type="hidden" name="id" value={d.id} />
                    <input type="hidden" name="action" value="reject" />
                    <input
                      type="text"
                      name="reason"
                      placeholder="Raison du refus (optionnel)"
                      maxLength={300}
                    />
                    <button type="submit" className="btn-reject-confirm">
                      Confirmer le refus
                    </button>
                  </form>
                </details>
              </div>
            )}
          </article>
        ))
      )}

      {/* 6. L'équipe — roster d'agents (pattern Claude Claw) */}
      <h2>L&apos;équipe</h2>
      <div className="agents">
        {AGENTS.map((a) => {
          const act = a.active ? lastAction(a.key) : null;
          return (
            <div key={a.key} className={`agent-card${a.active ? "" : " soon"}`}>
              <div className="agent-head">
                <span className={`agent-swatch ${a.key}`} />
                <span className="agent-card-name">{a.name}</span>
                <span className={`agent-state ${a.active ? "on" : "off"}`}>
                  {a.active ? "● actif" : "○ bientôt"}
                </span>
              </div>
              <div className="agent-role">{a.role}</div>
              <div className="agent-last">
                {a.active ? (
                  act ? (
                    <>
                      {act.text} <span className="when">· {act.when}</span>
                    </>
                  ) : (
                    "aucune action récente"
                  )
                ) : (
                  "en préparation"
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 7. Fil d'activité — timeline avec dots colorés par agent */}
      <h2>
        Fil d&apos;activité
        {data.feed.length > 0 && <span className="count">{data.feed.length}</span>}
      </h2>
      {data.feed.length === 0 ? (
        <div className="empty">
          <span className="empty-dot" />
          Journée calme — rien à signaler.
        </div>
      ) : (
        <ul className="feed">
          {data.feed.map((e, i) => (
            <li key={i}>
              <span className={`tdot ${e.agent}`} />
              <div className="entry">
                <div className="head">
                  <span className={`agent-ink ${e.agent}`}>{AGENT_NAME[e.agent]}</span>
                  <span className="when">{relTime(e.at, now)}</span>
                  {e.status && (
                    <span className={`status-pill ${e.status}`}>{statusFr(e.status)}</span>
                  )}
                </div>
                <div className="what">
                  {e.title} — <strong>{e.result}</strong>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* 8. Santé du système (pattern crons-monitoring, en langage humain) */}
      <section className="syshealth">
        <span className={`dot${staleHours > 36 ? " warn" : ""}`} />
        <span>
          {PIPELINES_COUNT} pipelines de données · dernière synchro il y a{" "}
          {relHoursLabel(staleHours)} · {SIGNALS_COUNT} signaux surveillés
        </span>
      </section>

      {/* Footer */}
      <footer className="footer">
        <span>Données : Supabase gigi-data-os · mise à jour auto toutes les 5 min</span>
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
