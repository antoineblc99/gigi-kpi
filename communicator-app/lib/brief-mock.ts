/**
 * Mock brief data — used by the design template to develop visuals offline.
 * Numbers are realistic Lea Gigi values from the 1-7 May 2026 window.
 */
import type { BriefData } from "./brief-types";

const today = "2026-05-08";
const weekAgo = "2026-05-01";

function spark(values: number[]): { series: { date: string; value: number }[] } {
  const start = new Date("2026-05-01");
  return {
    series: values.map((v, i) => {
      const d = new Date(start);
      d.setDate(d.getDate() + i);
      return { date: d.toISOString().slice(0, 10), value: v };
    }),
  };
}

export const MOCK_BRIEF: BriefData = {
  meta: {
    client: "Gigi Academy",
    client_slug: "lea-gigi",
    period_start: weekAgo,
    period_end: today,
    period_label: "7 derniers jours",
    generated_at: "2026-05-08T22:00:00.000Z",
    model: "claude-opus-4-7",
    tool_calls: 18,
    data_health_status: "yellow",
    cache_age_minutes: 11,
  },

  tldr: {
    punchline: "353€ → 12 calls → 6 ventes / 10 000€ contracté · ROAS cash 18x. Anaïs encaisse mal, Follow saigne sans attribution.",
    spend_total: { value: 353, prev_value: 355, delta_pct: -0.6, verdict: "neutral", unit: "eur" },
    calls_total: { value: 12, prev_value: 9, delta_pct: 33.3, verdict: "good", unit: "count" },
    ventes: { value: 6, prev_value: 3, delta_pct: 100, verdict: "good", unit: "count" },
    cash_collected: { value: 6500, prev_value: 4200, delta_pct: 54.8, verdict: "good", unit: "eur" },
    cash_contracted: { value: 10000, prev_value: 6000, delta_pct: 66.7, verdict: "good", unit: "eur" },
    roas_collected: { value: 18.4, prev_value: 11.8, delta_pct: 55.9, verdict: "good", unit: "ratio" },
    roas_contracted: { value: 28.3, prev_value: 16.9, delta_pct: 67.5, verdict: "good", unit: "ratio" },
    alerts: [
      { level: "warning", msg: "Encaissement initial Anaïs 38% — 3 700€ à recouvrer" },
      { level: "info", msg: "Funnel Follow: 91€ spend, 2 calls, attribution lead→ad indisponible" },
    ],
  },

  funnels: {
    vsl: {
      spend: { value: 261, prev_value: 294, delta_pct: -11.2, verdict: "neutral", unit: "eur" },
      spend_spark: spark([42, 38, 41, 35, 33, 38, 34]),
      opt_ins: { value: 146, prev_value: 92, delta_pct: 58.7, verdict: "good", unit: "count" },
      cpl_opt_in: { value: 1.79, prev_value: 3.2, delta_pct: -44.1, verdict: "good", unit: "eur" },
      vsl_watched: { value: 77, prev_value: 51, delta_pct: 51.0, verdict: "good", unit: "count" },
      rate_watched: { value: 52.7, prev_value: 55.4, delta_pct: -4.9, verdict: "neutral", unit: "pct" },
      cost_per_vsl_watch: { value: 3.39, prev_value: 5.76, delta_pct: -41.1, verdict: "good", unit: "eur" },
      leads_chauds: { value: 28, prev_value: 18, delta_pct: 55.6, verdict: "good", unit: "count" },
      rate_lead_chaud: { value: 36.4, prev_value: 35.3, delta_pct: 3.1, verdict: "good", unit: "pct" },
      calls_booked: { value: 10, prev_value: 9, delta_pct: 11.1, verdict: "good", unit: "count" },
      cost_per_call: { value: 26.1, prev_value: 32.7, delta_pct: -20.2, verdict: "good", unit: "eur" },
      top_ad: {
        ad_id: "120243478948140073",
        name: "GIGI_VSL_VIDEO_VALUE_4_RETARGET",
        spend: 41,
        leads_attributed: 9,
        wins: 1,
        cpl: 4.58,
        cost_per_sale: 41,
      },
      drain: undefined,
      recommendation: "Scaler VSL_VIDEO_VALUE_4_RETARGET de 41€→60€/jour. ROAS 49x sur cette ad seule.",
    },
    follow: {
      spend: { value: 91, prev_value: 61, delta_pct: 49.2, verdict: "warning", unit: "eur" },
      spend_spark: spark([12, 13, 11, 14, 15, 13, 13]),
      followers_gained: { value: 642, prev_value: 580, delta_pct: 10.7, verdict: "good", unit: "count" },
      followers_total: 19497,
      calls_booked: { value: 2, prev_value: 4, delta_pct: -50, verdict: "bad", unit: "count" },
      cost_per_call: { value: 45.6, prev_value: 15.3, delta_pct: 198, verdict: "bad", unit: "eur" },
      top_ad: undefined,
      drain: {
        ad_id: "120243479012345678",
        name: "GIGI_FOLLOW_VIDEO_STORY_80EUROS_BROAD",
        spend: 47,
        leads_attributed: 0,
        wins: 0,
      },
      recommendation: "Couper FOLLOW_STORY_80EUROS_BROAD (47€/sem, 0 attribution mesurable).",
    },
  },

  closing: {
    closers: [
      {
        closer_name: "Anaïs Bruneel",
        calls_planifies: 8,
        calls_recus: 6,
        show_rate_pct: 75,
        ventes: 4,
        ventes_setting: 1,
        ventes_vsl: 3,
        cash_contracted: 6000,
        cash_collected: 2300,
        encaissement_pct: 38.3,
        fathom_count: 5,
      },
      {
        closer_name: "Audrey Cuni",
        calls_planifies: 0,
        calls_recus: 0,
        show_rate_pct: 0,
        ventes: 2,
        ventes_setting: 2,
        ventes_vsl: 0,
        cash_contracted: 4000,
        cash_collected: 2200,
        encaissement_pct: 55,
        fathom_count: 0,
      },
    ],
    totals: {
      calls_planifies: 8,
      calls_recus: 6,
      show_rate_pct: 75,
      ventes: 6,
      cash_contracted: 10000,
      cash_collected: 4500,
      encaissement_pct: 45,
    },
    eod_missing_today: [],
  },

  pipeline: {
    by_stage: [
      { stage_name: "New Lead (A appeler)", count: 320, pipeline_value_eur: 640000 },
      { stage_name: "Form filled", count: 233, pipeline_value_eur: 466000 },
      { stage_name: "R1 Planifié", count: 21, pipeline_value_eur: 42000 },
      { stage_name: "R1 No show", count: 20, pipeline_value_eur: 40000 },
      { stage_name: "R2 Planifié", count: 13, pipeline_value_eur: 26000 },
      { stage_name: "Follow Up (< 2 semaines)", count: 16, pipeline_value_eur: 32000 },
      { stage_name: "Follow Up Long Terme", count: 59, pipeline_value_eur: 118000 },
      { stage_name: "Gagné", count: 17, pipeline_value_eur: 34000 },
      { stage_name: "Perdu", count: 15, pipeline_value_eur: 0 },
      { stage_name: "Annulé/Disqualifié", count: 23, pipeline_value_eur: 0 },
    ],
    by_funnel: {
      vsl: { leads_unique: 148, opps: 159, wins: 1 },
      setting: { leads_unique: 1, opps: 1, wins: 0 },
    },
  },

  attribution: {
    top_by_spend: [
      { rank: 1, ad_id: "1", name: "VSL_VIDEO_STORY_80EUROS_BROAD", spend: 55, leads_attributed: 23, wins: 0, cpl: 2.39, funnel: "VSL" },
      { rank: 2, ad_id: "2", name: "FOLLOW_VIDEO_STORY_80EUROS_BROAD", spend: 47, leads_attributed: 0, wins: 0, funnel: "Follow" },
      { rank: 3, ad_id: "3", name: "VSL_VIDEO_STORY_80EUROS_RETARGETING", spend: 45, leads_attributed: 28, wins: 0, cpl: 1.61, funnel: "VSL" },
      { rank: 4, ad_id: "4", name: "VSL_VIDEO_VALUE_4_RETARGET", spend: 41, leads_attributed: 9, wins: 1, cpl: 4.58, cost_per_sale: 41, funnel: "VSL" },
      { rank: 5, ad_id: "5", name: "VSL_VIDEO_STORY_Temoignage1_BROAD", spend: 37, leads_attributed: 14, wins: 0, cpl: 2.67, funnel: "VSL" },
    ],
    winner: {
      rank: 4, ad_id: "4", name: "VSL_VIDEO_VALUE_4_RETARGET", spend: 41,
      leads_attributed: 9, wins: 1, cpl: 4.58, cost_per_sale: 41, funnel: "VSL",
    },
    drain: {
      rank: 2, ad_id: "2", name: "FOLLOW_VIDEO_STORY_80EUROS_BROAD", spend: 47,
      leads_attributed: 0, wins: 0, funnel: "Follow",
    },
  },

  actions: [
    {
      rank: 1,
      owner: "Léa",
      deadline: "Lundi 08/05",
      action: "Scaler VSL_VIDEO_VALUE_4_RETARGET de 41€→60€/jour, dupliquer en BROAD pour test",
      impact_eur: 800,
      category: "marketing",
    },
    {
      rank: 2,
      owner: "Léa",
      deadline: "Lundi 08/05",
      action: "Couper FOLLOW_VIDEO_STORY_80EUROS_BROAD, réinjecter 50% sur VSL retarget",
      impact_eur: 200,
      category: "marketing",
    },
    {
      rank: 3,
      owner: "Anaïs",
      deadline: "Mercredi 10/05",
      action: "Appeler les 3 No-show + recouvrir les 4 acomptes incomplets (3 700€)",
      impact_eur: 3700,
      category: "sales",
    },
  ],
};
