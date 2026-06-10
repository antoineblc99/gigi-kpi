/**
 * Signals agent — détecte les signaux business actionnables et les poste dans Slack.
 *
 * Contrairement au validator (intégrité data), ici on regarde le BUSINESS :
 * show rate, leads chauds qui dorment, encaissement, capacity, CPL, ads qui brûlent.
 *
 * Philosophie : silence = tout va bien. On ne poste QUE s'il y a au moins un signal.
 */
import { runReadOnlySQL } from "@/lib/sql";

export type SignalSeverity = "yellow" | "red";

export type Signal = {
  id: string;
  severity: SignalSeverity;
  title: string;
  value: string;     // valeur observée
  threshold: string; // seuil franchi
  action: string;    // action suggérée
  details?: string;  // ex: liste d'emails / noms d'ads
};

async function q(query: string): Promise<any[]> {
  const { rows, error } = await runReadOnlySQL(query);
  if (error) throw new Error(`SQL: ${error}`);
  return rows;
}

// Lignes EOD sentinel (test Typeform : même valeur partout) — exclues des agrégats,
// même filtre que validator.ts.
const EOD_SENTINEL_FILTER = `NOT (calls_planifies > 0 AND calls_planifies = calls_recus
  AND calls_planifies = ventes_setting AND calls_planifies = ventes_vsl
  AND calls_planifies::numeric = cash_contracte)`;

// ============================================================================
// 1. SHOW RATE 7j — calls_recus / calls_planifies (EOD closeuses)
// ============================================================================
async function checkShowRate(): Promise<Signal[]> {
  const rows = await q(`
    SELECT COALESCE(sum(calls_recus), 0)::int AS recus,
           COALESCE(sum(calls_planifies), 0)::int AS planifies
    FROM fact_eod_closeuse
    WHERE submit_date >= current_date - interval '7 days'
      AND ${EOD_SENTINEL_FILTER}
  `);
  const recus = Number(rows[0]?.recus ?? 0);
  const planifies = Number(rows[0]?.planifies ?? 0);
  if (planifies === 0) return []; // pas de data EOD → freshness, c'est le job du validator
  const rate = (recus / planifies) * 100;
  if (rate >= 60) return [];
  return [
    {
      id: "show_rate_7d",
      severity: rate < 50 ? "red" : "yellow",
      title: "SHOW RATE 7j",
      value: `${rate.toFixed(0)}% (${recus}/${planifies})`,
      threshold: "< 60% (cible 70-85%)",
      action: "Renforcer la séquence de confirmation J-1/J-Day (SMS + rappel closeuse)",
    },
  ];
}

// ============================================================================
// 2. LEADS CHAUDS NON BOOKÉS — survey qualifié 14j, aucun call, soumis il y a >48h
// ============================================================================
async function checkHotLeadsUnbooked(): Promise<Signal[]> {
  const rows = await q(`
    SELECT s.lead_id, s.email, max(s.submitted_at) AS submitted_at
    FROM fact_survey s
    WHERE s.submitted_at >= now() - interval '14 days'
      AND s.submitted_at < now() - interval '48 hours'
      AND (s.quand_demarrer ILIKE '%Tout de suite%' OR s.quand_demarrer ILIKE '%30 prochains%')
      AND s.budget ILIKE 'Oui%'
      AND NOT EXISTS (
        SELECT 1 FROM fact_call c
        WHERE c.lead_id = s.lead_id AND c.status != 'cancelled'
      )
    GROUP BY s.lead_id, s.email
    ORDER BY max(s.submitted_at) DESC
  `);
  const n = rows.length; // 1 ligne = 1 lead_id distinct (GROUP BY)
  if (n <= 10) return [];
  const top5 = rows.slice(0, 5).map((r) => r.email || r.lead_id).join(", ");
  return [
    {
      id: "hot_leads_unbooked",
      severity: n > 25 ? "red" : "yellow",
      title: "LEADS CHAUDS NON BOOKÉS",
      value: `${n} leads qualifiés sans call depuis >48h (fenêtre 14j)`,
      threshold: "> 10 (red > 25)",
      action: "Setter : rappeler/DM ces leads en priorité aujourd'hui",
      details: `5 plus récents : ${top5}`,
    },
  ];
}

// ============================================================================
// 3. ACOMPTES INCOMPLETS — ratio cash_collecte / cash_contracte 7j (EOD)
// ============================================================================
async function checkCollectionRatio(): Promise<Signal[]> {
  const rows = await q(`
    SELECT COALESCE(sum(cash_collecte), 0)::numeric AS collecte,
           COALESCE(sum(cash_contracte), 0)::numeric AS contracte
    FROM fact_eod_closeuse
    WHERE submit_date >= current_date - interval '7 days'
      AND ${EOD_SENTINEL_FILTER}
  `);
  const collecte = Number(rows[0]?.collecte ?? 0);
  const contracte = Number(rows[0]?.contracte ?? 0);
  if (contracte === 0) return [];
  const ratio = (collecte / contracte) * 100;
  if (ratio >= 70) return [];
  return [
    {
      id: "collection_ratio_7d",
      severity: "yellow",
      title: "ENCAISSEMENT INITIAL 7j",
      value: `${ratio.toFixed(0)}% (${collecte.toFixed(0)}€ collectés / ${contracte.toFixed(0)}€ contractés)`,
      threshold: "< 70%",
      action: "Durcir le recouvrement : acompte minimum au call, relance J+1 sur les impayés",
    },
  ];
}

// ============================================================================
// 4. INCOHÉRENCE EOD vs GHL — ventes EOD 7j vs fact_sale Gagné 7j
// ============================================================================
async function checkEodVsGhl(): Promise<Signal[]> {
  const rows = await q(`
    WITH eod AS (
      SELECT COALESCE(sum(ventes_setting + ventes_vsl), 0)::int n
      FROM fact_eod_closeuse
      WHERE submit_date >= current_date - interval '7 days'
        AND ${EOD_SENTINEL_FILTER}
    ),
    ghl AS (
      SELECT count(*)::int n FROM fact_sale
      WHERE is_won = true AND updated_at >= current_date - interval '7 days'
    )
    SELECT eod.n eod_n, ghl.n ghl_n FROM eod, ghl
  `);
  const eod = Number(rows[0]?.eod_n ?? 0);
  const ghl = Number(rows[0]?.ghl_n ?? 0);
  const mx = Math.max(eod, ghl);
  if (mx === 0) return [];
  const gap = Math.abs(eod - ghl);
  // gap minimum de 2 ventes pour éviter le bruit sur petits volumes (1 vs 2 = 50% mais non actionnable)
  if (gap / mx <= 0.3 || gap < 2) return [];
  return [
    {
      id: "eod_vs_ghl_sales_7d",
      severity: "yellow",
      title: "INCOHÉRENCE EOD vs GHL 7j",
      value: `EOD ${eod} ventes vs GHL ${ghl} Gagné (écart ${Math.round((gap / mx) * 100)}%)`,
      threshold: "écart > 30%",
      action:
        eod > ghl
          ? "Closeuses : passer les opportunités gagnées en 'Gagné' dans la pipeline GHL"
          : "Closeuses : remplir l'EOD du soir (ventes non déclarées)",
    },
  ];
}

// ============================================================================
// 5. CAPACITY — prochains 7j, règle Anaïs partagée : MAX(slots_free) + SUM(slots_booked)
// ============================================================================
async function checkCapacity(): Promise<Signal[]> {
  const rows = await q(`
    WITH latest AS (
      SELECT DISTINCT ON (calendar_id, target_date)
        calendar_id, target_date, slots_free, slots_booked
      FROM fact_calendar_capacity
      WHERE target_date >= current_date AND target_date < current_date + interval '7 days'
      ORDER BY calendar_id, target_date, snapshot_at DESC
    ),
    per_day AS (
      SELECT target_date,
             MAX(slots_free)::int AS free,    -- slots partagés Anaïs = MAX, jamais SUM
             SUM(slots_booked)::int AS booked -- bookings uniques par calendar = SUM
      FROM latest
      GROUP BY target_date
    )
    SELECT COALESCE(SUM(booked), 0)::int booked, COALESCE(SUM(free), 0)::int free
    FROM per_day
  `);
  const booked = Number(rows[0]?.booked ?? 0);
  const free = Number(rows[0]?.free ?? 0);
  const total = booked + free;
  if (total === 0) return []; // pas de snapshot → validator s'en charge
  const util = (booked / total) * 100;
  // Seuils KPI_REGISTRY §9 : 70-85% optimal, <50% lead-constrained, >90% sales-constrained
  if (util > 90) {
    return [
      {
        id: "capacity_7d",
        severity: "yellow",
        title: "CAPACITY 7j",
        value: `${util.toFixed(0)}% utilisée (${booked} bookés / ${free} libres)`,
        threshold: "> 90% — sales-constrained",
        action: "Ouvrir des slots ou activer une 2e closeuse",
      },
    ];
  }
  if (util < 50) {
    return [
      {
        id: "capacity_7d",
        severity: "yellow",
        title: "CAPACITY 7j",
        value: `${util.toFixed(0)}% utilisée (${booked} bookés / ${free} libres)`,
        threshold: "< 50% — lead-constrained",
        action: "Scaler les ads ou améliorer la qualif pour remplir le calendrier",
      },
    ];
  }
  return [];
}

// ============================================================================
// 6. CPL DRIFT — proxy CPL = spend / contacts créés (fact_contact), 3j vs 7j précédents
// (fact_ad_daily n'a pas d'opt-ins fiables — pixel vsl_optin sur-compte)
// ============================================================================
async function checkCplDrift(): Promise<Signal[]> {
  const rows = await q(`
    WITH spend AS (
      SELECT
        COALESCE(sum(spend) FILTER (WHERE date >= current_date - 3 AND date < current_date), 0)::numeric AS s3,
        COALESCE(sum(spend) FILTER (WHERE date >= current_date - 10 AND date < current_date - 3), 0)::numeric AS s7
      FROM fact_ad_daily
    ),
    contacts AS (
      SELECT
        count(DISTINCT lead_id) FILTER (WHERE date_added >= current_date - 3 AND date_added < current_date)::int AS c3,
        count(DISTINCT lead_id) FILTER (WHERE date_added >= current_date - 10 AND date_added < current_date - 3)::int AS c7
      FROM fact_contact
    )
    SELECT s.s3, s.s7, c.c3, c.c7 FROM spend s, contacts c
  `);
  const r = rows[0] ?? {};
  const s3 = Number(r.s3 ?? 0);
  const s7 = Number(r.s7 ?? 0);
  const c3 = Number(r.c3 ?? 0);
  const c7 = Number(r.c7 ?? 0);
  if (s7 === 0 || c7 === 0) return []; // pas de baseline
  const cplBase = s7 / c7;
  if (c3 === 0) {
    if (s3 < 50) return []; // spend négligeable, pas de signal
    return [
      {
        id: "cpl_drift",
        severity: "red",
        title: "CPL DRIFT 3j",
        value: `${s3.toFixed(0)}€ dépensés, 0 contact créé`,
        threshold: `CPL infini vs ${cplBase.toFixed(2)}€ baseline`,
        action: "Vérifier le tracking GHL + couper les adsets sans opt-in",
      },
    ];
  }
  const cpl3 = s3 / c3;
  const drift = (cpl3 / cplBase - 1) * 100;
  if (drift < 50) return [];
  return [
    {
      id: "cpl_drift",
      severity: drift >= 100 ? "red" : "yellow",
      title: "CPL DRIFT 3j",
      value: `${cpl3.toFixed(2)}€ vs ${cplBase.toFixed(2)}€ baseline 7j (+${drift.toFixed(0)}%)`,
      threshold: "+50% (red +100%)",
      action: "Audit créas/audiences : couper les adsets qui dérivent, relancer une créa fraîche",
    },
  ];
}

// ============================================================================
// 7. AD QUI BRÛLE — spend 30j > 300€ et 0 vente attribuée (utm_content → lead → sale won)
// ============================================================================
async function checkBurningAds(): Promise<Signal[]> {
  const rows = await q(`
    WITH ad_spend AS (
      SELECT ad_id, sum(spend)::numeric AS spend30
      FROM fact_ad_daily
      WHERE date >= current_date - 30
      GROUP BY ad_id
      HAVING sum(spend) > 300
    ),
    ad_sales AS (
      SELECT c.utm_content AS ad_id, count(DISTINCT s.lead_id)::int AS won
      FROM fact_contact c
      JOIN fact_sale s ON s.lead_id = c.lead_id AND s.is_won = true
      WHERE c.utm_content IS NOT NULL
      GROUP BY c.utm_content
    )
    SELECT a.ad_id, a.spend30, COALESCE(d.name, a.ad_id) AS ad_name
    FROM ad_spend a
    LEFT JOIN ad_sales sa ON sa.ad_id = a.ad_id
    LEFT JOIN dim_ad d ON d.ad_id = a.ad_id
    WHERE COALESCE(sa.won, 0) = 0
    ORDER BY a.spend30 DESC
  `);
  if (!rows.length) return [];
  const list = rows
    .slice(0, 5)
    .map((r) => `${r.ad_name} (${Number(r.spend30).toFixed(0)}€)`)
    .join(" · ");
  return [
    {
      id: "burning_ads",
      severity: "yellow",
      title: "ADS QUI BRÛLENT",
      value: `${rows.length} ad(s) > 300€ sur 30j sans aucune vente attribuée`,
      threshold: "spend 30j > 300€ et 0 vente",
      action: "Couper ou retravailler ces ads",
      details: list,
    },
  ];
}

// ============================================================================
// 8. CTR DECAY — ads actives (spend 3j > 0) dont CTR 3j < 60% du CTR 14j
// ============================================================================
async function checkCtrDecay(): Promise<Signal[]> {
  const rows = await q(`
    WITH win AS (
      SELECT ad_id,
        sum(clicks) FILTER (WHERE date >= current_date - 3)::numeric AS clicks3,
        sum(impressions) FILTER (WHERE date >= current_date - 3)::numeric AS imp3,
        sum(spend) FILTER (WHERE date >= current_date - 3)::numeric AS spend3,
        sum(clicks)::numeric AS clicks14,
        sum(impressions)::numeric AS imp14
      FROM fact_ad_daily
      WHERE date >= current_date - 14
      GROUP BY ad_id
    )
    SELECT w.ad_id, COALESCE(d.name, w.ad_id) AS ad_name,
           round(100.0 * w.clicks3 / w.imp3, 2) AS ctr3,
           round(100.0 * w.clicks14 / w.imp14, 2) AS ctr14
    FROM win w
    LEFT JOIN dim_ad d ON d.ad_id = w.ad_id
    WHERE COALESCE(w.spend3, 0) > 0
      AND w.imp3 >= 1000              -- assez d'impressions pour que le CTR 3j soit significatif
      AND w.imp14 > 0 AND w.clicks14 > 0
      AND (w.clicks3 / w.imp3) < 0.6 * (w.clicks14 / w.imp14)
    ORDER BY w.imp3 DESC
  `);
  if (!rows.length) return [];
  const list = rows
    .slice(0, 5)
    .map((r) => `${r.ad_name} (${r.ctr3}% vs ${r.ctr14}%)`)
    .join(" · ");
  return [
    {
      id: "ctr_decay",
      severity: "yellow",
      title: "CTR DECAY",
      value: `${rows.length} créa(s) fatiguée(s) : CTR 3j < 60% du CTR 14j`,
      threshold: "CTR 3j < 60% × CTR 14j",
      action: "Préparer des variantes (nouveau hook) avant que le CPL ne dérive",
      details: list,
    },
  ];
}

// ============================================================================
// SLACK
// ============================================================================
function buildSlackBlocks(signals: Signal[]): any[] {
  const dateStr = new Date().toLocaleDateString("fr-FR", {
    timeZone: "Europe/Paris",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const line = (s: Signal) =>
    `• *${s.title}* — ${s.value} (seuil : ${s.threshold})\n  → ${s.action}${s.details ? `\n  _${s.details}_` : ""}`;

  const reds = signals.filter((s) => s.severity === "red");
  const yellows = signals.filter((s) => s.severity === "yellow");

  const blocks: any[] = [
    {
      type: "header",
      text: { type: "plain_text", text: `🚦 Signaux Gigi — ${dateStr}`, emoji: true },
    },
  ];
  if (reds.length) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `🔴 *Critique*\n${reds.map(line).join("\n\n")}` },
    });
  }
  if (yellows.length) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `🟡 *À surveiller*\n${yellows.map(line).join("\n\n")}` },
    });
  }
  blocks.push({
    type: "context",
    elements: [
      {
        type: "mrkdwn",
        text: `Signals · ${reds.length}🔴 ${yellows.length}🟡 · ${new Date().toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}`,
      },
    ],
  });
  return blocks;
}

// ============================================================================
// MAIN
// ============================================================================
export type SignalsRunResult = {
  ran_at: string;
  total: number;
  red: number;
  yellow: number;
  signals: Signal[];
  errors: string[];
  posted_to_slack: boolean;
};

const CHECKS: Array<{ name: string; fn: () => Promise<Signal[]> }> = [
  { name: "show_rate", fn: checkShowRate },
  { name: "hot_leads_unbooked", fn: checkHotLeadsUnbooked },
  { name: "collection_ratio", fn: checkCollectionRatio },
  { name: "eod_vs_ghl", fn: checkEodVsGhl },
  { name: "capacity", fn: checkCapacity },
  { name: "cpl_drift", fn: checkCplDrift },
  { name: "burning_ads", fn: checkBurningAds },
  { name: "ctr_decay", fn: checkCtrDecay },
];

export async function runSignals(): Promise<SignalsRunResult> {
  const ranAt = new Date().toISOString();
  const signals: Signal[] = [];
  const errors: string[] = [];

  for (const check of CHECKS) {
    try {
      signals.push(...(await check.fn()));
    } catch (e: any) {
      // un check qui plante ne doit pas bloquer les autres ni générer un faux signal
      errors.push(`${check.name}: ${String(e?.message ?? e).slice(0, 150)}`);
    }
  }

  // tri : reds d'abord
  signals.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "red" ? -1 : 1));

  const red = signals.filter((s) => s.severity === "red").length;
  const yellow = signals.filter((s) => s.severity === "yellow").length;

  let posted = false;
  // Silence = tout va bien : on ne poste QUE s'il y a au moins un signal
  if (signals.length > 0 && process.env.SLACK_WEBHOOK_URL) {
    await fetch(process.env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        blocks: buildSlackBlocks(signals),
        text: `Signaux Gigi : ${red} rouge(s), ${yellow} jaune(s)`,
      }),
    })
      .then(() => {
        posted = true;
      })
      .catch((e) => console.error("Slack push failed", e));
  }

  return {
    ran_at: ranAt,
    total: signals.length,
    red,
    yellow,
    signals,
    errors,
    posted_to_slack: posted,
  };
}
