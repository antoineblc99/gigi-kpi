/**
 * Données de la vue client (/vue-client) — mêmes sources que le cockpit
 * (KPI_REGISTRY.md respecté : cash master = fact_eod_closeuse, sentinel exclu,
 * ventes = COUNT(DISTINCT lead_id)), mais récit 100 % client : pas de jargon
 * interne, pas de statuts de décisions, pas de santé système.
 */
import { sql } from "./sql";
import {
  EOD_SENTINEL_FILTER,
  SHOW_RATE_TARGET,
  SHOW_RATE_ALERT,
  formatEur,
  type Verdict,
} from "./data";
import { computeRoiLedger, type RoiLedger } from "./roi";

export type ClientStat = {
  label: string;
  display: string;
  sub: string;
  verdict: Verdict;
  action: string | null; // phrase d'action en cours si le chiffre est rouge
};

export type ClientViewData = {
  generatedAt: string;
  brief: string[];
  ledger: RoiLedger;
  stats: ClientStat[];
  error?: string;
};

export async function getClientViewData(): Promise<ClientViewData> {
  const now = new Date();
  const empty: ClientViewData = {
    generatedAt: now.toISOString(),
    brief: [],
    ledger: { measured_eur: 0, items: [], estimated_monthly_eur: 0 },
    stats: [],
  };

  try {
    const [cash30Rows, ventes30Rows, show7Rows, ledger] = await Promise.all([
      // Cash collecté 30 j — master cash (fact_eod_closeuse.cash_collecte)
      sql<{ collecte: number }>(`
        SELECT COALESCE(sum(cash_collecte), 0)::numeric AS collecte
        FROM fact_eod_closeuse
        WHERE submit_date >= current_date - interval $$30 days$$
          AND ${EOD_SENTINEL_FILTER}
      `),
      // Ventes 30 j — COUNT(DISTINCT lead_id), jamais COUNT(*)
      sql<{ ventes: number }>(`
        SELECT count(DISTINCT lead_id)::int AS ventes
        FROM fact_sale
        WHERE is_won AND contracted_at >= current_date - interval $$30 days$$
      `),
      // Show rate 7 j = calls_recus / calls_planifies (EOD)
      sql<{ recus: number; planifies: number }>(`
        SELECT COALESCE(sum(calls_recus), 0)::int AS recus,
               COALESCE(sum(calls_planifies), 0)::int AS planifies
        FROM fact_eod_closeuse
        WHERE submit_date >= current_date - interval $$7 days$$
          AND ${EOD_SENTINEL_FILTER}
      `),
      // Actions exécutées par le système → ROI ledger (mesuré dans les facts)
      computeRoiLedger(now),
    ]);

    const collecte30 = Number(cash30Rows[0]?.collecte ?? 0);
    const ventes30 = Number(ventes30Rows[0]?.ventes ?? 0);
    const recus = Number(show7Rows[0]?.recus ?? 0);
    const planifies = Number(show7Rows[0]?.planifies ?? 0);
    const showPct = planifies > 0 ? (recus / planifies) * 100 : null;
    const showLow = showPct !== null && showPct < SHOW_RATE_ALERT;

    // --- Chiffres business avec narratif (chiffre rouge → action en cours) ---
    const stats: ClientStat[] = [
      {
        label: "Cash encaissé · 30 jours",
        display: formatEur(collecte30),
        sub: "tout ce qui est réellement rentré sur les 30 derniers jours",
        verdict: "good",
        action: null,
      },
      {
        label: "Ventes · 30 jours",
        display: new Intl.NumberFormat("fr-FR").format(ventes30),
        sub: "clientes qui ont signé sur les 30 derniers jours",
        verdict: "good",
        action: null,
      },
      {
        label: "Appels honorés · 7 jours",
        display: showPct === null ? "—" : `${showPct.toFixed(0)} %`,
        sub:
          showPct === null
            ? "pas encore de données sur 7 jours"
            : `${recus} appels sur ${planifies} prévus ont bien eu lieu · objectif ${SHOW_RATE_TARGET} %`,
        verdict:
          showPct === null
            ? "warn"
            : showPct >= SHOW_RATE_TARGET
              ? "good"
              : showPct >= SHOW_RATE_ALERT
                ? "warn"
                : "bad",
        action:
          showPct !== null && showPct < SHOW_RATE_TARGET
            ? "Le système de rappels SMS arrive cette semaine pour faire remonter ce chiffre."
            : null,
      },
    ];

    // --- Brief en français simple (zéro jargon interne) ---
    const brief: string[] = [];
    brief.push(
      `Sur les 30 derniers jours : ${formatEur(collecte30)} encaissés et ${ventes30} vente${
        ventes30 > 1 ? "s" : ""
      } signée${ventes30 > 1 ? "s" : ""}.`
    );
    if (showPct !== null) {
      brief.push(
        showLow
          ? `Le point à améliorer : ${showPct.toFixed(0)} % des appels prévus ont bien eu lieu (objectif ${SHOW_RATE_TARGET} %). Le système de rappels SMS arrive cette semaine pour corriger ça.`
          : `${showPct.toFixed(0)} % des appels prévus ont bien eu lieu cette semaine (objectif ${SHOW_RATE_TARGET} %).`
      );
    }
    if (ledger.estimated_monthly_eur > 0) {
      brief.push(
        `De son côté, ton système a déjà réalloué ~${formatEur(
          ledger.estimated_monthly_eur
        )}/mois de budget pub vers ce qui vend.`
      );
    } else {
      brief.push("Ton système surveille tes pubs et tes prospects en continu — rien d'urgent de ton côté.");
    }

    return { generatedAt: now.toISOString(), brief, ledger, stats };
  } catch (e) {
    return { ...empty, error: String(e instanceof Error ? e.message : e) };
  }
}
