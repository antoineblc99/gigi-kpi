/**
 * Modèle de données du cockpit — toutes les requêtes respectent KPI_REGISTRY.md :
 *  - cash master = fact_eod_closeuse (jamais Whop + EOD)
 *  - filtre sentinel EOD identique à communicator-app (validator.ts / signals.ts)
 *  - volumes par lead = COUNT(DISTINCT lead_id)
 *  - attribution ad limitée au funnel VSL (Follow non attribuable ad-level)
 */
import { sql } from "./sql";

// Filtre sentinel EOD — copie exacte de communicator-app/lib/signals.ts
export const EOD_SENTINEL_FILTER = `NOT (calls_planifies > 0 AND calls_planifies = calls_recus
  AND calls_planifies = ventes_setting AND calls_planifies = ventes_vsl
  AND calls_planifies::numeric = cash_contracte)`;

export const PALIER_1 = 30_000;
export const PALIERS = [30_000, 60_000, 100_000];
// Santé système — pipelines/pull_*.py (gigi-kpi) + détecteurs signals.ts (communicator-app)
export const PIPELINES_COUNT = 10;
export const SIGNALS_COUNT = 8;
export const COLLECTION_RATE = 0.8; // strategy.md : ~80% du contracté finit collecté
export const SHOW_RATE_TARGET = 70; // cible strategy.md
export const SHOW_RATE_ALERT = 60; // seuil signal (signals.ts)

export type Verdict = "good" | "warn" | "bad";

export type Kpi = {
  label: string;
  value: number;
  display: string;
  sub: string;
  source: string; // table.colonne — règle justification source
  verdict: Verdict;
};

export type DecisionRow = {
  id: number;
  agent_name: string;
  decision_type: string;
  status: string;
  created_at: string;
  executed_by: string | null;
  payload: {
    title?: string;
    summary?: string;
    severity?: string;
    current?: string;
    actions?: string[];
    [k: string]: unknown;
  } | null;
  outcome: { result?: string; [k: string]: unknown } | null;
};

export type AdWaste = { name: string; ad_id: string; spend: number; ventes: number };

export type CallsTodayEntry = { label: string; calls: number };

export type FeedEntry = {
  agent: "observer" | "optimiseur" | "relanceur" | "stratege";
  at: string; // ISO
  title: string;
  result: string; // affiché en gras
  status?: string; // proposed / approved / executed
};

export type CockpitData = {
  generatedAt: string;
  // jauge palier
  contracteMtd: number;
  collecteAttenduMtd: number; // contracté MTD × 0.8
  projectionMois: number; // collecté attendu projeté fin de mois (rythme actuel)
  // KPI cards
  kpis: Kpi[];
  showRate7d: { recus: number; planifies: number; pct: number | null };
  // décisions
  decisionsProposed: DecisionRow[];
  decisionsRecent: DecisionRow[];
  // calls du jour (silence-si-vert : tableau vide → rien affiché)
  callsToday: CallsTodayEntry[];
  // signaux & fraîcheur
  adsWaste: AdWaste[];
  freshestPull: string | null;
  attentionCount: number;
  feed: FeedEntry[];
  brief: string[];
  error?: string;
};

function verdictOf(value: number, good: number, warn: number): Verdict {
  if (value >= good) return "good";
  if (value >= warn) return "warn";
  return "bad";
}

const eur = (n: number) =>
  new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Math.round(n)) + " €";

export async function getCockpitData(): Promise<CockpitData> {
  const now = new Date();
  const empty: CockpitData = {
    generatedAt: now.toISOString(),
    contracteMtd: 0,
    collecteAttenduMtd: 0,
    projectionMois: 0,
    kpis: [],
    showRate7d: { recus: 0, planifies: 0, pct: null },
    decisionsProposed: [],
    decisionsRecent: [],
    callsToday: [],
    adsWaste: [],
    freshestPull: null,
    attentionCount: 0,
    feed: [],
    brief: [],
  };

  try {
    const [mtdRows, cash30Rows, show7Rows, optinRows, decisionRows, freshRows, adsRows, callsTodayRows] =
      await Promise.all([
        // 1. Cash contracté mois courant (EOD, sentinel exclu)
        sql<{ contracte: number }>(`
          SELECT COALESCE(sum(cash_contracte), 0)::numeric AS contracte
          FROM fact_eod_closeuse
          WHERE submit_date >= date_trunc($$month$$, current_date)
            AND ${EOD_SENTINEL_FILTER}
        `),
        // 2. Cash collecté 30j — master cash (fact_eod_closeuse.cash_collecte)
        sql<{ collecte: number }>(`
          SELECT COALESCE(sum(cash_collecte), 0)::numeric AS collecte
          FROM fact_eod_closeuse
          WHERE submit_date >= current_date - interval $$30 days$$
            AND ${EOD_SENTINEL_FILTER}
        `),
        // 3. Show rate 7j = calls_recus / calls_planifies (EOD)
        sql<{ recus: number; planifies: number }>(`
          SELECT COALESCE(sum(calls_recus), 0)::int AS recus,
                 COALESCE(sum(calls_planifies), 0)::int AS planifies
          FROM fact_eod_closeuse
          WHERE submit_date >= current_date - interval $$7 days$$
            AND ${EOD_SENTINEL_FILTER}
        `),
        // 4. Opt-ins 30j — COUNT(DISTINCT lead_id), jamais COUNT(*)
        sql<{ optins: number }>(`
          SELECT count(DISTINCT lead_id)::int AS optins
          FROM fact_contact
          WHERE date_added >= current_date - interval $$30 days$$
        `),
        // 5. decision_log récents (toutes les sections en une requête)
        sql<DecisionRow>(`
          SELECT id, agent_name, decision_type, status, created_at, executed_by, payload, outcome
          FROM decision_log
          ORDER BY created_at DESC
          LIMIT 12
        `),
        // 6. Fraîcheur pipelines = MAX(pulled_at) sur les tables qui le portent
        sql<{ freshest: string | null }>(`
          SELECT max(mx) AS freshest FROM (
            SELECT max(pulled_at) mx FROM fact_contact
            UNION ALL SELECT max(pulled_at) FROM fact_sale
            UNION ALL SELECT max(pulled_at) FROM fact_call
            UNION ALL SELECT max(pulled_at) FROM fact_eod_closeuse
            UNION ALL SELECT max(pulled_at) FROM fact_survey
          ) t
        `),
        // 7. Ads VSL > 300 € / 30j sans vente attribuée
        //    (utm_content = ad_id → lead_id → fact_sale.is_won, COUNT DISTINCT)
        //    Funnel Follow exclu : non attribuable ad-level (KPI Registry §8)
        sql<AdWaste>(`
          WITH spend AS (
            SELECT f.ad_id, sum(f.spend) AS sp
            FROM fact_ad_daily f
            JOIN dim_ad d ON d.ad_id = f.ad_id
            WHERE f.date >= current_date - interval $$30 days$$
              AND d.name ILIKE $$%VSL%$$
            GROUP BY f.ad_id
            HAVING sum(f.spend) > 300
          ),
          sales AS (
            SELECT c.utm_content AS ad_id, count(DISTINCT s.lead_id) AS ventes
            FROM fact_sale s
            JOIN fact_contact c ON c.lead_id = s.lead_id
            WHERE s.is_won AND s.contracted_at >= current_date - interval $$30 days$$
            GROUP BY c.utm_content
          )
          SELECT d.name, sp.ad_id, round(sp.sp)::int AS spend, COALESCE(sa.ventes, 0)::int AS ventes
          FROM spend sp
          LEFT JOIN sales sa USING (ad_id)
          JOIN dim_ad d ON d.ad_id = sp.ad_id
          WHERE COALESCE(sa.ventes, 0) = 0
          ORDER BY sp.sp DESC
        `),
        // 8. Calls prévus aujourd'hui (Europe/Paris) par calendrier — fact_call,
        //    status != cancelled (KPI Registry §calls), COUNT(DISTINCT lead_id)
        sql<CallsTodayEntry>(`
          SELECT calendar_label AS label, count(DISTINCT lead_id)::int AS calls
          FROM fact_call
          WHERE (scheduled_at AT TIME ZONE $$Europe/Paris$$)::date
              = (now() AT TIME ZONE $$Europe/Paris$$)::date
            AND status NOT IN ($$cancelled$$)
          GROUP BY calendar_label
          ORDER BY calls DESC
        `),
      ]);

    const contracteMtd = Number(mtdRows[0]?.contracte ?? 0);
    const collecte30 = Number(cash30Rows[0]?.collecte ?? 0);
    const recus = Number(show7Rows[0]?.recus ?? 0);
    const planifies = Number(show7Rows[0]?.planifies ?? 0);
    const showPct = planifies > 0 ? (recus / planifies) * 100 : null;
    const optins30 = Number(optinRows[0]?.optins ?? 0);
    const decisionsRecent = decisionRows;
    const decisionsProposed = decisionRows.filter((d) => d.status === "proposed");
    const freshestPull = freshRows[0]?.freshest ?? null;
    const adsWaste = adsRows;
    const callsToday = callsTodayRows;

    // --- Jauge palier ---
    const collecteAttenduMtd = contracteMtd * COLLECTION_RATE;
    const dayOfMonth = now.getDate();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const projectionMois = dayOfMonth > 0 ? (collecteAttenduMtd / dayOfMonth) * daysInMonth : 0;

    // --- KPI cards (verdicts dérivés des cibles strategy.md, jamais décoratifs) ---
    // Palier 1 = 30k collectés/mois → cible 30j collecté (1ers paiements) ≈ 30k × 0.8
    const cashTarget30d = PALIER_1 * COLLECTION_RATE;
    // Palier 1 : ~65-76 calls planifiés/mois à 9,4% optin→call → ~700 opt-ins/mois
    const optinTarget30d = 700;

    const kpis: Kpi[] = [
      {
        label: "Cash collecté · 30 j",
        value: collecte30,
        display: eur(collecte30),
        sub: `cible palier 1 ≈ ${eur(cashTarget30d)} (1ers paiements)`,
        source: "fact_eod_closeuse.cash_collecte",
        verdict: verdictOf(collecte30, cashTarget30d, cashTarget30d * 0.6),
      },
      {
        label: "Show rate · 7 j",
        value: showPct ?? 0,
        display: showPct === null ? "—" : `${showPct.toFixed(0)} %`,
        sub:
          showPct === null
            ? "pas d'EOD sur 7 j"
            : `${recus}/${planifies} calls honorés · cible ${SHOW_RATE_TARGET} %`,
        source: "fact_eod_closeuse.calls_recus / calls_planifies",
        verdict: showPct === null ? "warn" : verdictOf(showPct, SHOW_RATE_TARGET, SHOW_RATE_ALERT),
      },
      {
        label: "Opt-ins · 30 j",
        value: optins30,
        display: new Intl.NumberFormat("fr-FR").format(optins30),
        sub: `cible palier 1 ≈ ${optinTarget30d}/mois`,
        source: "COUNT(DISTINCT fact_contact.lead_id)",
        verdict: verdictOf(optins30, optinTarget30d * 0.9, optinTarget30d * 0.6),
      },
    ];

    // --- Signaux inline (silence-si-vert) ---
    const staleHours = freshestPull
      ? (now.getTime() - new Date(freshestPull).getTime()) / 3_600_000
      : Infinity;
    const showRateLow = showPct !== null && showPct < SHOW_RATE_ALERT;

    const attentionCount =
      (showRateLow ? 1 : 0) +
      adsWaste.length +
      decisionsProposed.length +
      (staleHours > 36 ? 1 : 0);

    // --- Brief du jour (template strings, pas de LLM) ---
    const brief: string[] = [];
    brief.push(
      `À ce rythme : ~${eur(projectionMois)} collectés attendus ce mois-ci (${eur(
        contracteMtd
      )} contractés × 80 %) — ${
        projectionMois >= PALIER_1 ? "palier 1 (30 000 €) en ligne de mire" : `vs palier 1 : ${eur(PALIER_1)}`
      }.`
    );
    if (showRateLow && showPct !== null) {
      brief.push(
        `LE levier : le show rate — ${showPct.toFixed(0)} % sur 7 j (${recus}/${planifies}) pour une cible à ${SHOW_RATE_TARGET} %. Chaque call honoré en plus rapproche du palier sans dépenser un euro de plus.`
      );
    } else if (showPct !== null) {
      brief.push(
        `Show rate 7 j : ${showPct.toFixed(0)} % (${recus}/${planifies}) — au-dessus du seuil d'alerte, on garde le cap sur ${SHOW_RATE_TARGET} %.`
      );
    }
    if (adsWaste.length > 0) {
      const top = adsWaste[0];
      brief.push(
        `Point chaud : ${adsWaste.length === 1 ? "1 ad a" : `${adsWaste.length} ads ont`} dépensé plus de 300 € en 30 j sans vente attribuée — ${shortAdName(
          top.name
        )} (${eur(top.spend)}). L'Optimiseur a l'œil dessus.`
      );
    } else if (decisionsProposed.length > 0) {
      brief.push(
        `Point chaud : ${decisionsProposed.length} décision${
          decisionsProposed.length > 1 ? "s" : ""
        } en attente de validation (via WhatsApp).`
      );
    } else if (staleHours > 36) {
      brief.push(`Point chaud : données synchronisées il y a ${Math.round(staleHours)} h — pipeline à vérifier.`);
    } else {
      brief.push("Rien d'urgent aujourd'hui — le système tourne.");
    }

    // --- Fil d'activité ---
    const feed: FeedEntry[] = [];
    // (a) decision_log récents, tous statuts
    for (const d of decisionsRecent.slice(0, 8)) {
      feed.push({
        agent: agentKey(d.agent_name),
        at: d.created_at,
        title: humanizeAdNames(d.payload?.title || humanizeType(d.decision_type)),
        result: humanizeAdNames(feedResult(d)),
        status: d.status,
      });
    }
    // (b) fraîcheur pipelines — Observer
    if (freshestPull) {
      feed.push({
        agent: "observer",
        at: freshestPull,
        title: "Pipelines de données",
        result: `données synchronisées il y a ${relHoursLabel(staleHours)}`,
      });
    }
    // (c) signaux calculés inline — silence-si-vert
    if (showRateLow && showPct !== null) {
      feed.push({
        agent: "stratege",
        at: now.toISOString(),
        title: "Show rate 7 j sous le seuil",
        result: `${showPct.toFixed(0)} % (${recus}/${planifies}) — cible ${SHOW_RATE_TARGET} %`,
      });
    }
    for (const ad of adsWaste) {
      feed.push({
        agent: "optimiseur",
        at: now.toISOString(),
        title: `Ad sans vente attribuée : ${shortAdName(ad.name)}`,
        result: `${eur(ad.spend)} dépensés en 30 j · 0 vente`,
      });
    }
    feed.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

    return {
      generatedAt: now.toISOString(),
      contracteMtd,
      collecteAttenduMtd,
      projectionMois,
      kpis,
      showRate7d: { recus, planifies, pct: showPct },
      decisionsProposed,
      decisionsRecent,
      callsToday,
      adsWaste,
      freshestPull,
      attentionCount,
      feed,
      brief,
    };
  } catch (e) {
    return { ...empty, error: String(e instanceof Error ? e.message : e) };
  }
}

// ---------------------------------------------------------------------------

function agentKey(name: string): FeedEntry["agent"] {
  const n = (name || "").toLowerCase();
  if (n.includes("optim")) return "optimiseur";
  if (n.includes("relan")) return "relanceur";
  if (n.includes("strat")) return "stratege";
  return "observer";
}

export function humanizeType(type: string): string {
  const known: Record<string, string> = {
    pause_ad: "Proposition : couper une ad",
    scale_ad: "Proposition : scaler une ad",
    relance_leads: "Relance de leads chauds",
  };
  if (known[type]) return known[type];
  const t = (type || "décision").replace(/^anomaly:/, "anomalie : ").replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function feedResult(d: DecisionRow): string {
  if (d.status === "executed") {
    const r = d.outcome?.result;
    return r ? String(r) : `exécutée${d.executed_by ? ` par ${d.executed_by}` : ""}`;
  }
  if (d.status === "approved") return `validée${d.executed_by ? ` par ${d.executed_by}` : ""} — en cours`;
  if (d.status === "rejected") return "refusée";
  if (d.payload?.current) return String(d.payload.current);
  if (d.payload?.summary) return String(d.payload.summary);
  return "en attente de validation";
}

export function shortAdName(name: string): string {
  return (name || "").replace(/^GIGI_(VSL|FOLLOW)_VIDEO_STORY_/, "");
}

// Remplace les noms d'ads bruts (GIGI_VSL_VIDEO_STORY_…) dans un texte libre
// (titres/summaries de decision_log) — rendu uniquement, jamais la donnée.
export function humanizeAdNames(text: string): string {
  return (text || "").replace(/GIGI_(?:VSL|FOLLOW)_VIDEO_STORY_[A-Z0-9_-]+/g, (m) =>
    shortAdName(m)
  );
}

// Vocabulaire métier des calendriers (KPI Registry : Follow = calls de setting)
export function calendarLabelFr(label: string): string {
  if (label === "Follow") return "Setting";
  return label || "Autre";
}

export function relHoursLabel(hours: number): string {
  if (!isFinite(hours)) return "— jamais";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${Math.round(hours / 24)} j`;
}

export function relTime(iso: string, now = new Date()): string {
  const h = (now.getTime() - new Date(iso).getTime()) / 3_600_000;
  if (h < 0.05) return "à l'instant";
  if (h < 1) return `il y a ${Math.max(1, Math.round(h * 60))} min`;
  if (h < 24) return `il y a ${Math.round(h)} h`;
  const d = Math.round(h / 24);
  if (d === 1) return "hier";
  if (d < 31) return `il y a ${d} j`;
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(new Date(iso));
}

export function formatEur(n: number): string {
  return eur(n);
}
