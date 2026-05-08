/**
 * Brief data types — structured JSON output from brief.ts that the React Brief
 * component renders. Keep this file aligned with the design template.
 *
 * Design philosophy:
 *  - Every numeric field has a baseline (vs S-1) so charts/sparklines can show delta
 *  - Every "verdict" field uses controlled vocab: 'good' | 'warning' | 'bad' | 'neutral'
 *  - Series for sparklines = arrays of {date, value} (daily granularity, 7-30 days)
 *  - Currency always EUR, integers when possible
 */

// ============================================================================
// Primitives
// ============================================================================

export type Verdict = "good" | "warning" | "bad" | "neutral";

export type Severity = "info" | "warning" | "critical";

/** Daily timeseries point — used for sparklines */
export type Point = {
  date: string; // ISO date YYYY-MM-DD
  value: number;
};

/** Stat with delta vs previous period */
export type Stat = {
  value: number;
  prev_value?: number;
  delta_pct?: number; // (value - prev) / prev * 100, rounded 1 decimal
  verdict?: Verdict;
  unit?: "eur" | "count" | "pct" | "ratio" | "days";
};

/** Spark = small inline chart */
export type Spark = {
  series: Point[]; // 7-30 daily points
  baseline?: number; // optional reference line
};

// ============================================================================
// Meta — generation context
// ============================================================================

export type BriefMeta = {
  client: string; // "Gigi Academy"
  client_slug: string; // "lea-gigi"
  period_start: string; // ISO date "2026-05-01"
  period_end: string; // ISO date "2026-05-07"
  period_label: string; // "7 derniers jours"
  generated_at: string; // ISO datetime
  model: string; // "claude-opus-4-7"
  tool_calls: number; // SQL queries run
  data_health_status: "green" | "yellow" | "red"; // from data_health table
  cache_age_minutes?: number;
};

// ============================================================================
// TL;DR — top of brief
// ============================================================================

export type BriefTldr = {
  punchline: string; // 1 sentence < 120 chars
  spend_total: Stat; // EUR
  calls_total: Stat; // count
  ventes: Stat; // count
  cash_collected: Stat; // EUR
  cash_contracted: Stat; // EUR
  roas_collected: Stat; // ratio (cash_collected / spend)
  roas_contracted: Stat; // ratio
  alerts: Array<{ level: Severity; msg: string }>; // 0-3 alerts
};

// ============================================================================
// Ad — used inside funnel.top_ad / drain / attribution table
// ============================================================================

export type AdRef = {
  ad_id: string; // Meta ad ID
  name: string; // ad name
  spend: number; // EUR 7d
  leads_attributed?: number; // via utm_content
  wins?: number; // attributed wins
  cpl?: number; // EUR per lead
  cost_per_sale?: number; // EUR per win
  ctr_pct?: number;
};

// ============================================================================
// Funnels — VSL et Follow→Setting
// ============================================================================

export type FunnelVsl = {
  spend: Stat; // EUR
  spend_spark: Spark; // 7-30 daily points
  opt_ins: Stat; // fact_contact 7j attribué VSL via utm_content
  cpl_opt_in: Stat; // EUR per opt-in
  vsl_watched: Stat; // fact_survey 7j
  rate_watched: Stat; // % opt-ins → survey complete
  cost_per_vsl_watch: Stat;
  leads_chauds: Stat; // survey filtré ('tout de suite' + 'budget oui')
  rate_lead_chaud: Stat; // % survey → lead chaud
  calls_booked: Stat; // fact_call calendar 8ECq actifs
  cost_per_call: Stat;
  top_ad?: AdRef;
  drain?: AdRef; // ad qui draine spend sans résultat
  recommendation?: string; // 1 phrase action
};

export type FunnelFollow = {
  spend: Stat;
  spend_spark: Spark;
  followers_gained: Stat; // fact_ig_followers 7j (compte total IG, ads + organic mêlés)
  followers_total: number; // current total IG @giginails77
  calls_booked: Stat; // fact_call calendar AQ8R actifs
  cost_per_call: Stat; // attention: spend mêlé organic-ads peut fausser
  top_ad?: AdRef;
  drain?: AdRef;
  recommendation?: string;
};

export type Funnels = {
  vsl: FunnelVsl;
  follow: FunnelFollow;
};

// ============================================================================
// Closing — per closeuse table + encaissement
// ============================================================================

export type CloserStat = {
  closer_name: string; // "Anaïs Bruneel"
  calls_planifies: number; // RDV programmés agenda 7j
  calls_recus: number; // shows réels
  show_rate_pct: number;
  ventes: number; // total split = setting + vsl
  ventes_setting: number;
  ventes_vsl: number;
  cash_contracted: number; // EUR signé 7j
  cash_collected: number; // EUR encaissé 7j (1er paiement)
  encaissement_pct: number; // collected / contracted (peut dépasser 100% si solde)
  fathom_count: number; // recordings disponibles
};

export type ClosingSection = {
  closers: CloserStat[];
  totals: {
    calls_planifies: number;
    calls_recus: number;
    show_rate_pct: number;
    ventes: number;
    cash_contracted: number;
    cash_collected: number;
    encaissement_pct: number;
  };
  eod_missing_today: string[]; // closeuses qui n'ont pas soumis l'EOD aujourd'hui
};

// ============================================================================
// Pipeline GHL — distribution stages
// ============================================================================

export type PipelineStage = {
  stage_name: string; // "R1 Planifié", "R1 No show", etc.
  count: number;
  pipeline_value_eur: number; // sum monetary_value à ce stade
  funnel?: "VSL" | "Setting"; // if filterable by source_funnel
};

export type PipelineSection = {
  by_stage: PipelineStage[]; // ordonné par flux: New Lead → Form filled → R1 Planifié → R1 No show → R2 Planifié → Gagné/Perdu
  by_funnel: {
    vsl: { leads_unique: number; opps: number; wins: number };
    setting: { leads_unique: number; opps: number; wins: number };
  };
};

// ============================================================================
// Attribution top ads — cross-funnel ranking
// ============================================================================

export type AttributionTopAd = AdRef & {
  funnel?: "VSL" | "Follow";
  rank: number; // 1..N
};

export type AttributionSection = {
  top_by_spend: AttributionTopAd[]; // top 5-10 by spend 7j
  winner: AttributionTopAd | null; // ad with best CPS
  drain: AttributionTopAd | null; // ad with >100€ spend, 0 attribution
};

// ============================================================================
// Actions — 3 priorities
// ============================================================================

export type ActionItem = {
  rank: 1 | 2 | 3;
  owner: string; // "Léa", "Anaïs", "Toi"
  deadline: string; // human-readable, e.g. "Lundi 08/05"
  action: string; // verb-first impératif
  impact_eur?: number; // estimated EUR impact
  category: "marketing" | "sales" | "ops" | "data";
};

// ============================================================================
// Whole brief
// ============================================================================

export type BriefData = {
  meta: BriefMeta;
  tldr: BriefTldr;
  funnels: Funnels;
  closing: ClosingSection;
  pipeline: PipelineSection;
  attribution: AttributionSection;
  actions: ActionItem[];
  /** Optional fallback markdown if structured generation fails — design template
   *  should hide everything else and render this as a plain markdown card. */
  fallback_markdown?: string;
};

// ============================================================================
// Helpers (pure functions — no React deps)
// ============================================================================

export function verdictForDelta(delta_pct: number, higherIsBetter = true): Verdict {
  if (Math.abs(delta_pct) < 5) return "neutral";
  if (higherIsBetter) {
    return delta_pct > 0 ? "good" : "bad";
  }
  return delta_pct < 0 ? "good" : "bad";
}

export function formatEur(n: number, opts: { compact?: boolean } = {}): string {
  if (opts.compact && Math.abs(n) >= 1000) {
    return `${(n / 1000).toFixed(1)}k€`;
  }
  return `${Math.round(n).toLocaleString("fr-FR")}€`;
}

export function formatPct(n: number): string {
  return `${n.toFixed(1).replace(".", ",")}%`;
}

export function formatRatio(n: number): string {
  return `${n.toFixed(1).replace(".", ",")}x`;
}
