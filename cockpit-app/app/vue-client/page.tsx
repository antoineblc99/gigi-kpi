import type { Metadata } from "next";
import { getClientViewData } from "@/lib/client-data";
import { formatEur, type Verdict } from "@/lib/data";
import clientActions from "@/config/client-actions.json";

/**
 * Vue client — ce que Léa voit. Même data que le cockpit, autre récit :
 * français simple, actions exécutées avec leur résultat, ses chiffres
 * business, et ce qu'on attend d'elle. Rien d'interne ici (pas de santé
 * système, pas de file de décisions, pas de boutons opérateur).
 */
export const revalidate = 300;

export const metadata: Metadata = {
  title: "Ton système — Gigi Academy",
  description: "Gigi Academy — Ton système, Powered by Scale.IA",
  robots: { index: false, follow: false },
};

type ClientAction = { titre: string; detail: string; depuis: string };

const STATUS_FR: Record<Verdict, string> = {
  good: "En piste",
  warn: "En retard",
  bad: "Hors piste",
};

function sinceLabel(iso: string): string {
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long" }).format(new Date(iso));
}

export default async function VueClient() {
  const data = await getClientViewData();
  const actions = clientActions as ClientAction[];
  const now = new Date(data.generatedAt);

  const dateLabel = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Europe/Paris",
  }).format(now);

  return (
    <main className="container vc">
      {/* Header */}
      <header className="header">
        <div>
          <div className="eyebrow">Gigi Academy</div>
          <h1>Ton système</h1>
          <div className="header-date">{dateLabel}</div>
        </div>
        <span className="powered vc-powered">
          Powered by <strong>Scale.IA</strong>
        </span>
      </header>

      {data.error && (
        <div className="data-error">
          Les chiffres sont momentanément indisponibles. Réessaie dans quelques minutes.
        </div>
      )}

      {/* 1. Brief en français simple */}
      {data.brief.length > 0 && (
        <section className="brief">
          <div className="label">Où on en est</div>
          {data.brief.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </section>
      )}

      {/* 2. Ce que le système a fait pour toi */}
      <h2>Ce que le système a fait pour toi</h2>
      {data.ledger.items.length === 0 ? (
        <div className="empty">
          <span className="empty-dot" />
          Le système surveille tout en continu — première action très bientôt.
        </div>
      ) : (
        <>
          <ul className="vc-ledger">
            {data.ledger.items
              .filter((item) => item.kind === "measured")
              .map((item, i) => (
                <li key={i}>
                  <span className="vc-check" aria-hidden>
                    ✓
                  </span>
                  <span>{item.label ?? item.detail}</span>
                </li>
              ))}
          </ul>
          {data.ledger.estimated_monthly_eur > 0 && (
            <div className="vc-ledger-total">
              Impact estimé : <strong>~{formatEur(data.ledger.estimated_monthly_eur)}/mois</strong>{" "}
              de budget pub qui repart vers ce qui vend.
            </div>
          )}
        </>
      )}

      {/* 3. Tes chiffres */}
      <h2>Tes chiffres</h2>
      <div className="kpis">
        {data.stats.map((s) => (
          <div key={s.label} className="kpi">
            <div className="label">
              <span>{s.label}</span>
              <span className={`pill pill-${s.verdict}`}>{STATUS_FR[s.verdict]}</span>
            </div>
            <div className="value">{s.display}</div>
            <div className="sub">{s.sub}</div>
            {s.action && <div className="vc-action-note">{s.action}</div>}
          </div>
        ))}
      </div>

      {/* 4. On a besoin de toi */}
      <h2>
        On a besoin de toi
        {actions.length > 0 && <span className="count">{actions.length}</span>}
      </h2>
      {actions.length === 0 ? (
        <div className="empty">
          <span className="empty-dot" />
          Rien de ton côté pour le moment.
        </div>
      ) : (
        actions.map((a) => (
          <article key={a.titre} className="decision vc-need">
            <div className="top">
              <div className="title">{a.titre}</div>
              <span className="vc-since">depuis le {sinceLabel(a.depuis)}</span>
            </div>
            <div className="impact">{a.detail}</div>
          </article>
        ))
      )}

      {/* 5. Rapport de résultats */}
      <a
        className="vc-report"
        href="https://gigi-resultats.vercel.app"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span>
          <strong>Ton rapport de résultats</strong>
          <small>le détail complet de tes performances, mis à jour en continu</small>
        </span>
        <span className="vc-report-arrow" aria-hidden>
          →
        </span>
      </a>

      {/* Footer */}
      <footer className="footer">
        <span>Mis à jour automatiquement plusieurs fois par jour</span>
        <span className="powered">
          Powered by <strong>Scale.IA</strong>
        </span>
      </footer>
    </main>
  );
}
