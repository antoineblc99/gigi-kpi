/**
 * ROI Ledger — la valeur générée par l'AIOS, calculée depuis la data,
 * jamais déclarée. Source unique pour le cockpit opérateur ET la vue client.
 *
 * Deux catégories étanches (honnêteté absolue) :
 *
 *  - "measured" : vérifié dans les facts APRÈS l'action.
 *      · pause_ad exécutée → économie réelle = spend quotidien moyen pré-pause
 *        (payload.spend_eur / fenêtre) × jours PLEINS écoulés depuis la pause,
 *        MOINS le spend réellement constaté après la pause (fact_ad_daily —
 *        doit tomber à ~0, on le vérifie et on l'affiche). Le jour de la pause
 *        est exclu des deux côtés (spend partiel pré-pause non séparable) :
 *        on ne sur-déclare jamais.
 *      · relance_batch approuvée → calls bookés = COUNT(DISTINCT lead_id) des
 *        leads du payload avec un fact_call (status != cancelled) créé APRÈS
 *        l'approbation ; cash = fact_sale.is_won sur ces leads après
 *        approbation × 0,8 (règle d'or collecté).
 *
 *  - "estimated" : projection mensuelle des pauses actives (spend pré-pause
 *      ramené à 30 j). Jamais additionnée au mesuré.
 *
 * Total affiché = measured_eur uniquement. estimated_monthly_eur en sous-texte.
 */
import { sql } from "./sql";
import { COLLECTION_RATE } from "./data";

export type RoiItem = {
  date: string; // ISO — exécution / approbation
  agent: string;
  action: string;
  detail: string; // phrase opérateur, chiffres vérifiables
  value_eur?: number; // arrondi à l'euro
  metric?: string; // pour les items sans € (ex : "2 calls bookés")
  kind: "measured" | "estimated";
  label?: string; // phrase client zéro-jargon (vue-client)
};

export type RoiLedger = {
  measured_eur: number;
  items: RoiItem[];
  estimated_monthly_eur: number;
};

type LedgerDecision = {
  id: number;
  agent_name: string;
  decision_type: string;
  status: string;
  created_at: string;
  payload: {
    ad_id?: string;
    ad_name?: string;
    spend_eur?: number;
    projection_eur_mois?: number;
    window?: { days?: number };
    leads?: Array<{ lead_id?: string }>;
    summary?: string;
    [k: string]: unknown;
  } | null;
  outcome: {
    executed?: boolean;
    executed_at?: string;
    acted_at?: string;
    [k: string]: unknown;
  } | null;
};

const DAY_MS = 86_400_000;
const safeId = (s: string) => /^[a-zA-Z0-9_-]+$/.test(s);

// YYYY-MM-DD en Europe/Paris (les dates fact_ad_daily sont des jours calendaires)
const parisDay = (d: Date) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris" }).format(d);

function fullDaysSince(iso: string, now: Date): number {
  const from = new Date(parisDay(new Date(iso)) + "T00:00:00Z").getTime();
  const to = new Date(parisDay(now) + "T00:00:00Z").getTime();
  return Math.max(0, Math.round((to - from) / DAY_MS));
}

const DAYS_FR = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];

export function dayLabelFr(iso: string, now = new Date()): string {
  const dt = new Date(iso);
  const days = Math.floor((now.getTime() - dt.getTime()) / DAY_MS);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "hier";
  if (days < 7) return DAYS_FR[dt.getDay()];
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long" }).format(dt);
}

export async function computeRoiLedger(now = new Date()): Promise<RoiLedger> {
  const items: RoiItem[] = [];
  let measured = 0;
  let estimatedMonthly = 0;

  // Décisions génératrices de valeur : exécutées, ou relances approuvées
  // (une relance approuvée part aux leads — l'effet se mesure dans fact_call).
  const decisions = await sql<LedgerDecision>(`
    SELECT id, agent_name, decision_type, status, created_at, payload, outcome
    FROM decision_log
    WHERE (outcome->>$$executed$$) = $$true$$
       OR status = $$executed$$
       OR (decision_type = $$relance_batch$$ AND status IN ($$approved$$, $$executed$$))
    ORDER BY created_at
  `);

  for (const d of decisions) {
    if (d.decision_type === "pause_ad") {
      const adId = String(d.payload?.ad_id ?? "");
      const at = d.outcome?.executed_at || d.outcome?.acted_at || d.created_at;
      const spendStopped = Number(d.payload?.spend_eur ?? 0);
      const windowDays = Number(d.payload?.window?.days ?? 30) || 30;
      const dailyAvg = spendStopped / windowDays;
      if (!adId || !safeId(adId) || !(spendStopped > 0)) continue;

      // Vérification dans les facts : spend constaté APRÈS le jour de la pause
      const postRows = await sql<{ sp: number }>(`
        SELECT COALESCE(sum(spend), 0)::numeric AS sp
        FROM fact_ad_daily
        WHERE ad_id = $$${adId}$$ AND date > $$${parisDay(new Date(at))}$$::date
      `);
      const postSpend = Number(postRows[0]?.sp ?? 0);
      const days = fullDaysSince(at, now);
      const saved = Math.max(0, dailyAvg * days - postSpend);
      measured += saved;

      const adName = String(d.payload?.ad_name ?? adId);
      const projection = Number(d.payload?.projection_eur_mois ?? 0) || dailyAvg * 30;
      estimatedMonthly += projection;

      items.push({
        date: at,
        agent: d.agent_name,
        action: "Ad coupée",
        detail:
          `${adName} — ${Math.round(spendStopped)} € dépensés sur ${windowDays} j pré-pause ` +
          `(~${dailyAvg.toFixed(1)} €/j) · économisé réel : ${Math.round(saved)} € en ` +
          `${days} jour${days > 1 ? "s" : ""} plein${days > 1 ? "s" : ""} ` +
          `(spend constaté après pause : ${Math.round(postSpend)} €)`,
        value_eur: Math.round(saved),
        kind: "measured",
        label: `Une publicité qui dépensait sans vendre a été coupée ${dayLabelFr(at, now)} → ~${Math.round(
          projection
        )} €/mois réalloués vers ce qui vend.`,
      });
      items.push({
        date: at,
        agent: d.agent_name,
        action: "Projection pause",
        detail: `${adName} — ~${Math.round(projection)} €/mois économisés si la pause tient`,
        value_eur: Math.round(projection),
        kind: "estimated",
      });
    } else if (d.decision_type === "relance_batch") {
      const at = d.outcome?.acted_at || d.outcome?.executed_at || d.created_at;
      const leadIds = (d.payload?.leads ?? [])
        .map((l) => String(l?.lead_id ?? ""))
        .filter((id) => id && safeId(id));
      if (leadIds.length === 0) continue;
      const inList = leadIds.map((id) => `$$${id}$$`).join(", ");
      const approvedTs = new Date(at).toISOString();

      const [callRows, saleRows] = await Promise.all([
        // Calls bookés mesurés — COUNT(DISTINCT lead_id), status != cancelled,
        // créés APRÈS l'approbation (KPI Registry : jamais COUNT(*))
        sql<{ calls: number }>(`
          SELECT count(DISTINCT lead_id)::int AS calls
          FROM fact_call
          WHERE lead_id IN (${inList})
            AND created_at > $$${approvedTs}$$::timestamptz
            AND status NOT IN ($$cancelled$$)
        `),
        // Ventes won sur ces leads après approbation → cash contracté réel
        sql<{ cash: number; ventes: number }>(`
          SELECT COALESCE(sum(monetary_value), 0)::numeric AS cash,
                 count(DISTINCT lead_id)::int AS ventes
          FROM fact_sale
          WHERE is_won AND lead_id IN (${inList})
            AND contracted_at > $$${approvedTs}$$::timestamptz
        `),
      ]);

      const calls = Number(callRows[0]?.calls ?? 0);
      const cash = Number(saleRows[0]?.cash ?? 0);
      const ventes = Number(saleRows[0]?.ventes ?? 0);
      const cashAttendu = cash * COLLECTION_RATE;
      measured += cashAttendu;

      const parts = [`${calls} call${calls > 1 ? "s" : ""} booké${calls > 1 ? "s" : ""}`];
      if (ventes > 0)
        parts.push(
          `${ventes} vente${ventes > 1 ? "s" : ""} (${Math.round(cash)} € contractés × 80 %)`
        );
      items.push({
        date: at,
        agent: d.agent_name,
        action: "Relance de leads",
        detail: `${leadIds.length} leads relancés — ${parts.join(" · ")} depuis l'approbation`,
        ...(cashAttendu > 0
          ? { value_eur: Math.round(cashAttendu) }
          : { metric: `${calls} call${calls > 1 ? "s" : ""} booké${calls > 1 ? "s" : ""}` }),
        kind: "measured",
        label: `${leadIds.length} prospects chauds relancés ${dayLabelFr(at, now)} → ${parts.join(" et ")} depuis.`,
      });
    } else {
      // Autres actions exécutées : pas de valeur € mesurable, on les liste
      const at = d.outcome?.executed_at || d.outcome?.acted_at || d.created_at;
      const summary = typeof d.payload?.summary === "string" ? d.payload.summary : null;
      items.push({
        date: at,
        agent: d.agent_name,
        action: "Action exécutée",
        detail: summary || d.decision_type,
        metric: "exécutée",
        kind: "measured",
        label: summary || `Action exécutée ${dayLabelFr(at, now)}.`,
      });
    }
  }

  items.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  return {
    measured_eur: Math.round(measured),
    items,
    estimated_monthly_eur: Math.round(estimatedMonthly),
  };
}
