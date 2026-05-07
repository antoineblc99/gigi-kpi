/**
 * Anomaly detection rules — Observer agent V1
 *
 * Each rule receives a fresh metrics snapshot and returns an Anomaly | null.
 * Rules are pure functions: testable, composable. No side effects.
 *
 * Add a new rule = add an entry to RULES below + a detect function.
 */
import { runReadOnlySQL } from "@/lib/sql";

export type Severity = "critical" | "warning" | "info";

export type Anomaly = {
  rule_id: string;
  category: "meta" | "ghl" | "closing" | "eod" | "payment";
  severity: Severity;
  title: string;
  summary: string;          // 1 sentence diagnosis
  current: string;          // e.g. "CPL VSL 7j = 56,80€"
  baseline: string;         // e.g. "Bench < 20€ · moyenne 30j 42,10€"
  context_md: string;       // markdown bullets with detail
  actions: string[];        // 2-3 short suggested actions
  payload: Record<string, unknown>;  // structured context for decision_log
};

type Ctx = Record<string, never>;  // no shared context for now

async function q(query: string): Promise<any[]> {
  const { rows, error } = await runReadOnlySQL(query);
  if (error) throw new Error(`SQL: ${error}`);
  return rows;
}

// ============================================================================
// RULE 1 — CPL VSL too high (7-day rolling)
// ============================================================================
async function ruleCplVslHigh(): Promise<Anomaly | null> {
  const rows = await q(`
    SELECT COALESCE(SUM(spend), 0) AS spend,
           COALESCE(SUM(vsl_call_booked), 0) AS calls
    FROM fact_ad_daily f
    JOIN dim_ad a ON a.ad_id = f.ad_id
    WHERE f.date >= current_date - interval '7 days'
      AND a.name ILIKE '%VSL%'
  `);
  const spend = Number(rows[0]?.spend ?? 0);
  const calls = Number(rows[0]?.calls ?? 0);
  if (spend < 100) return null;          // skip if too small sample
  if (calls === 0) {
    return {
      rule_id: "cpl_vsl_zero_calls",
      category: "meta",
      severity: "critical",
      title: "Aucun call VSL sur 7 jours",
      summary: `${spend.toFixed(0)}€ dépensés sur les ads VSL en 7j sans 1 seul call booké`,
      current: `Spend 7j: ${spend.toFixed(0)}€ · Calls: 0`,
      baseline: "Bench: au moins 5-10 calls VSL/semaine attendus",
      context_md: `- 0 \`vsl_call_booked\` event sur 7j\n- Possible bug pixel ou page booking cassée\n- Vérifier le tracking + Tester le funnel`,
      actions: [
        "Tester le funnel VSL → booking en navigation privée",
        "Vérifier que VSL_Call_Booked event fire toujours dans Pixel Helper",
        "Pause ads VSL en attendant fix",
      ],
      payload: { spend_7j: spend, calls_7j: 0 },
    };
  }
  const cpl = spend / calls;
  if (cpl <= 50) return null;
  return {
    rule_id: "cpl_vsl_high",
    category: "meta",
    severity: cpl > 100 ? "critical" : "warning",
    title: `CPL VSL élevé : ${cpl.toFixed(2)}€/call`,
    summary: `Sur 7j, ${spend.toFixed(0)}€ pour ${calls} calls = ${cpl.toFixed(2)}€/call (objectif <20€)`,
    current: `CPL 7j: ${cpl.toFixed(2)}€`,
    baseline: "Objectif: < 20€ · Excellent: < 10€",
    context_md: `- Spend 7j: ${spend.toFixed(0)}€\n- Calls bookés: ${calls}\n- Pixel sous-compte typiquement → vrai CPL ~50% moins`,
    actions: [
      "Identifier les ads VSL avec CPL > 80€ et les pauser",
      "Scaler les top performers (CPL < 30€)",
      "Vérifier que le pixel VSL_Call_Booked fire bien (sinon CPL apparent ≠ réel)",
    ],
    payload: { spend_7j: spend, calls_7j: calls, cpl_7j: cpl },
  };
}

// ============================================================================
// RULE 2 — Cost per follower Follow too high
// ============================================================================
async function ruleCostFollowerHigh(): Promise<Anomaly | null> {
  const rows = await q(`
    SELECT COALESCE(SUM(spend), 0) AS spend,
           COALESCE(SUM(followers_ig), 0) AS followers
    FROM fact_ad_daily f
    JOIN dim_ad a ON a.ad_id = f.ad_id
    WHERE f.date >= current_date - interval '7 days'
      AND (a.name ILIKE '%Follow%' OR a.name ILIKE '%BROAD%' OR a.name ILIKE '%LAL%')
  `);
  const spend = Number(rows[0]?.spend ?? 0);
  const followers = Number(rows[0]?.followers ?? 0);
  if (spend < 100 || followers === 0) return null;
  const cpf = spend / followers;
  if (cpf <= 1.5) return null;
  return {
    rule_id: "cost_follower_high",
    category: "meta",
    severity: cpf > 2.5 ? "critical" : "warning",
    title: `Coût/follower élevé : ${cpf.toFixed(2)}€`,
    summary: `Sur 7j, ${spend.toFixed(0)}€ pour ${followers} followers IG = ${cpf.toFixed(2)}€/follower (bench 1,08€)`,
    current: `Coût/follower 7j: ${cpf.toFixed(2)}€`,
    baseline: "Bench historique: 1,08€ Broad · 1,25€ Lookalike",
    context_md: `- Spend Follow 7j: ${spend.toFixed(0)}€\n- Followers IG: ${followers}\n- Possible : audiences saturées, créa fatiguée, ou hausse CPM Meta`,
    actions: [
      "Couper les ads Follow avec coût/follower > 2€",
      "Lancer 2-3 nouvelles créas inspirées des winners (VALUE_4, VALUE_1)",
      "Vérifier la fréquence — si > 3, audience saturée",
    ],
    payload: { spend_7j: spend, followers_7j: followers, cpf_7j: cpf },
  };
}

// ============================================================================
// RULE 3 — Show rate drop (EOD closeuses)
// ============================================================================
async function ruleShowRateDrop(): Promise<Anomaly | null> {
  const rows = await q(`
    SELECT COALESCE(SUM(calls_planifies), 0) AS planifies,
           COALESCE(SUM(calls_recus), 0) AS recus
    FROM fact_eod_closeuse
    WHERE submit_date >= current_date - interval '7 days'
  `);
  const planifies = Number(rows[0]?.planifies ?? 0);
  const recus = Number(rows[0]?.recus ?? 0);
  if (planifies < 5) return null;
  const showRate = recus / planifies;
  if (showRate >= 0.6) return null;
  return {
    rule_id: "show_rate_drop",
    category: "closing",
    severity: showRate < 0.5 ? "critical" : "warning",
    title: `Show rate ${(showRate * 100).toFixed(0)}% (objectif 70%+)`,
    summary: `Sur 7j: ${recus}/${planifies} calls reçus = ${(showRate * 100).toFixed(0)}% show rate`,
    current: `Show rate 7j: ${(showRate * 100).toFixed(0)}%`,
    baseline: "Objectif: > 70% · Excellent: > 85%",
    context_md: `- Calls planifiés 7j: ${planifies}\n- Calls reçus 7j: ${recus}\n- No-shows: ${planifies - recus}\n- Chaque no-show ≈ 400€ contracté potentiel perdu (close 22% × 2000€)`,
    actions: [
      "Activer SMS rappel J-1 sur calendriers GHL",
      "Appel manuel J-0 (30 min avant) sur les leads chauds",
      "Cadeau d'ouverture (PDF, mini-formation) envoyé J-1 pour engagement",
    ],
    payload: { planifies_7j: planifies, recus_7j: recus, show_rate_7j: showRate },
  };
}

// ============================================================================
// RULE 4 — EOD manquant aujourd'hui
// ============================================================================
async function ruleEodMissing(): Promise<Anomaly | null> {
  // toLocaleString FR can return "11" or "11 h" — use a robust extractor.
  const parisStr = new Date().toLocaleString("en-GB", {
    hour: "2-digit",
    hour12: false,
    timeZone: "Europe/Paris",
  });
  const match = parisStr.match(/(\d{1,2})/);
  const hourParis = match ? Number(match[1]) : 12;
  if (hourParis < 22) return null; // only check after 22h Paris

  const rows = await q(`
    SELECT closer_name, COUNT(*) AS n
    FROM fact_eod_closeuse
    WHERE submit_date = current_date
    GROUP BY 1
  `);
  const submitted = new Set(rows.map((r) => r.closer_name as string));
  const expected = ["Anaïs Bruneel", "Audrey Cuni"];
  const missing = expected.filter((n) => !submitted.has(n));
  if (missing.length === 0) return null;
  return {
    rule_id: "eod_missing",
    category: "eod",
    severity: "warning",
    title: `EOD manquant : ${missing.join(", ")}`,
    summary: `Après 22h Paris, ${missing.length}/${expected.length} closeuses n'ont pas soumis leur EOD aujourd'hui`,
    current: `Soumis: ${[...submitted].join(", ") || "personne"}`,
    baseline: "Toutes les closeuses actives doivent soumettre avant 22h",
    context_md: `- Closeuse(s) absente(s): ${missing.join(", ")}\n- EOD manquant = data du jour incomplète, ROAS faussé`,
    actions: [
      `DM Slack rappel à ${missing.join(", ")}`,
      "Vérifier si elles ont reçu le formulaire Tally aujourd'hui",
      "Si récurrent: ajouter pénalité dans contrat closeuse",
    ],
    payload: { missing, submitted: [...submitted] },
  };
}

// ============================================================================
// RULE 5 — Spend ad spike sans résultat
// ============================================================================
async function ruleSpendSpikeNoResult(): Promise<Anomaly | null> {
  const rows = await q(`
    WITH last_7 AS (
      SELECT a.ad_id, a.name,
             SUM(f.spend) AS spend_7j,
             SUM(f.vsl_call_booked) AS calls_7j,
             SUM(f.followers_ig) AS followers_7j
      FROM fact_ad_daily f
      JOIN dim_ad a ON a.ad_id = f.ad_id
      WHERE f.date >= current_date - interval '7 days'
      GROUP BY a.ad_id, a.name
    )
    SELECT * FROM last_7
    WHERE spend_7j > 100
      AND COALESCE(calls_7j, 0) + COALESCE(followers_7j, 0) = 0
    ORDER BY spend_7j DESC
    LIMIT 5
  `);
  if (rows.length === 0) return null;
  const total = rows.reduce((s, r) => s + Number(r.spend_7j), 0);
  const top = rows.map(
    (r) => `- \`${r.name}\` — ${Number(r.spend_7j).toFixed(0)}€ pour 0 résultat`,
  ).join("\n");
  return {
    rule_id: "spend_no_result",
    category: "meta",
    severity: total > 500 ? "critical" : "warning",
    title: `${rows.length} ad(s) drainent du spend sans résultat`,
    summary: `${rows.length} ads ont >100€ spend sur 7j et 0 call/follower attribué (total ${total.toFixed(0)}€ gaspillés)`,
    current: `${rows.length} ads · ${total.toFixed(0)}€ gaspillés 7j`,
    baseline: "Toute ad >100€ devrait produire ≥1 résultat",
    context_md: `Top offenders:\n${top}`,
    actions: [
      `Pause ces ${rows.length} ads ce soir`,
      "Réallouer le budget sur les top performers (CPL < 30€)",
      "Si une ad récente: vérifier que le Pixel fire (peut-être tracking cassé)",
    ],
    payload: { ads: rows.map((r) => ({ ad_id: r.ad_id, name: r.name, spend: r.spend_7j })) },
  };
}

// ============================================================================
// RULE 6 — Cash collecté << contracté (signal recouvrement)
// ============================================================================
async function ruleRecouvrementGap(): Promise<Anomaly | null> {
  const rows = await q(`
    SELECT COALESCE(SUM(cash_contracte), 0) AS contr,
           COALESCE(SUM(cash_collecte), 0) AS coll
    FROM fact_eod_closeuse
    WHERE submit_date >= current_date - interval '30 days'
  `);
  const contr = Number(rows[0]?.contr ?? 0);
  const coll = Number(rows[0]?.coll ?? 0);
  if (contr < 5000) return null;
  const ratio = coll / contr;
  if (ratio >= 0.75) return null;
  const gap = contr - coll;
  return {
    rule_id: "recouvrement_gap",
    category: "payment",
    severity: ratio < 0.5 ? "critical" : "warning",
    title: `Recouvrement ${(ratio * 100).toFixed(0)}% — ${gap.toFixed(0)}€ en attente`,
    summary: `Sur 30j: ${contr.toFixed(0)}€ contracté, ${coll.toFixed(0)}€ collecté = ${gap.toFixed(0)}€ en pending`,
    current: `Recouvrement: ${(ratio * 100).toFixed(0)}%`,
    baseline: "Objectif: > 75% en 30j (carte + virement)",
    context_md: `- Cash contracté 30j: ${contr.toFixed(0)}€\n- Cash collecté 30j: ${coll.toFixed(0)}€\n- Pending: ${gap.toFixed(0)}€\n- Si > 30 jours, risque d'impayé`,
    actions: [
      "Lister les opportunités won sans paiement complet > 14 jours",
      "Workflow GHL relance auto J+3, J+7, J+14",
      "Appel manuel Anaïs sur les > 30j",
    ],
    payload: { contr_30j: contr, coll_30j: coll, ratio_30j: ratio, gap },
  };
}

// ============================================================================
// REGISTRY
// ============================================================================
export const RULES: Array<() => Promise<Anomaly | null>> = [
  ruleCplVslHigh,
  ruleCostFollowerHigh,
  ruleShowRateDrop,
  ruleEodMissing,
  ruleSpendSpikeNoResult,
  ruleRecouvrementGap,
];

export async function detectAll(): Promise<Anomaly[]> {
  const results = await Promise.allSettled(RULES.map((fn) => fn()));
  const anomalies: Anomaly[] = [];
  for (const r of results) {
    if (r.status === "fulfilled" && r.value) anomalies.push(r.value);
    if (r.status === "rejected") console.error("[observer] rule failed:", r.reason);
  }
  // Sort: critical → warning → info
  const order: Record<Severity, number> = { critical: 0, warning: 1, info: 2 };
  return anomalies.sort((a, b) => order[a.severity] - order[b.severity]);
}
