/**
 * Validator agent — runs after each pull to verify data integrity.
 *
 * Checks 3 dimensions:
 *  1. Freshness: each fact_* table has data ≤ N hours old
 *  2. Volume: row count today ≥ baseline 7d avg × threshold
 *  3. Cross-source coherence: orthogonal sources should converge within tolerance
 *
 * Outputs to data_health table + optional Slack ping if any check is red.
 * No false-positive philosophy: yellow = degraded but not blocking, red = analytic
 * routines should refuse to run.
 */
import { sb, runReadOnlySQL } from "@/lib/sql";

export type CheckStatus = "green" | "yellow" | "red";

export type CheckResult = {
  check_name: string;
  status: CheckStatus;
  expected: string;
  observed: string;
  delta_pct?: number;
  notes?: string;
};

async function q(query: string): Promise<any[]> {
  const { rows, error } = await runReadOnlySQL(query);
  if (error) throw new Error(`SQL: ${error}`);
  return rows;
}

// ============================================================================
// FRESHNESS — each table's max date should be recent
// ============================================================================
const FRESHNESS_TARGETS: Array<{ table: string; ts_col: string; max_age_hours: number; severity: "yellow" | "red" }> = [
  { table: "fact_ad_daily",      ts_col: "date",          max_age_hours: 36,  severity: "red" },
  { table: "fact_contact",       ts_col: "date_added",    max_age_hours: 36,  severity: "red" },
  { table: "fact_sale",          ts_col: "updated_at",    max_age_hours: 36,  severity: "red" },
  { table: "fact_call",          ts_col: "scheduled_at",  max_age_hours: 168, severity: "yellow" }, // future bookings dominate
  { table: "fact_survey",        ts_col: "submitted_at",  max_age_hours: 72,  severity: "yellow" },
  { table: "fact_eod_closeuse",  ts_col: "submit_date",   max_age_hours: 48,  severity: "yellow" },
  { table: "fact_payment",       ts_col: "paid_at",       max_age_hours: 168, severity: "yellow" }, // monthly CSV manual
];

async function checkFreshness(): Promise<CheckResult[]> {
  const out: CheckResult[] = [];
  for (const cfg of FRESHNESS_TARGETS) {
    try {
      const rows = await q(
        `SELECT max(${cfg.ts_col})::timestamptz mx, count(*)::int n FROM ${cfg.table};`,
      );
      const mx = rows[0]?.mx ? new Date(rows[0].mx) : null;
      const n = Number(rows[0]?.n ?? 0);
      const ageH = mx ? (Date.now() - mx.getTime()) / (3600 * 1000) : Infinity;
      const isStale = ageH > cfg.max_age_hours;
      out.push({
        check_name: `freshness:${cfg.table}`,
        status: isStale ? cfg.severity : "green",
        expected: `≤ ${cfg.max_age_hours}h old`,
        observed: mx ? `${ageH.toFixed(1)}h old (${n} rows)` : "EMPTY",
        notes: isStale ? `Run pull_${cfg.table.replace("fact_", "")}` : undefined,
      });
    } catch (e: any) {
      out.push({
        check_name: `freshness:${cfg.table}`,
        status: "red",
        expected: "table accessible",
        observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
      });
    }
  }
  return out;
}

// ============================================================================
// VOLUME — today's pull volume vs 7d baseline
// ============================================================================
async function checkVolume(): Promise<CheckResult[]> {
  const out: CheckResult[] = [];
  try {
    const rows = await q(`
      WITH today_count AS (
        SELECT count(*) AS n FROM fact_ad_daily WHERE date = current_date - 1
      ),
      baseline AS (
        SELECT avg(n)::numeric AS avg_n FROM (
          SELECT date, count(*) n FROM fact_ad_daily
          WHERE date BETWEEN current_date - 8 AND current_date - 2
          GROUP BY date
        ) s
      )
      SELECT t.n today_n, b.avg_n FROM today_count t, baseline b
    `);
    const todayN = Number(rows[0]?.today_n ?? 0);
    const avgN = Number(rows[0]?.avg_n ?? 0);
    if (avgN === 0) {
      out.push({
        check_name: "volume:fact_ad_daily",
        status: "yellow",
        expected: "non-zero baseline",
        observed: `today=${todayN}, baseline empty`,
      });
    } else {
      const deltaPct = ((todayN - avgN) / avgN) * 100;
      const status: CheckStatus = deltaPct < -50 ? "red" : deltaPct < -30 ? "yellow" : "green";
      out.push({
        check_name: "volume:fact_ad_daily",
        status,
        expected: `≈ ${avgN.toFixed(0)} rows/day (7d avg)`,
        observed: `${todayN} rows (D-1)`,
        delta_pct: Math.round(deltaPct * 10) / 10,
      });
    }
  } catch (e: any) {
    out.push({
      check_name: "volume:fact_ad_daily",
      status: "red",
      expected: "queryable",
      observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
    });
  }
  return out;
}

// ============================================================================
// COHERENCE — cross-source sanity checks
// ============================================================================
async function checkCoherence(): Promise<CheckResult[]> {
  const out: CheckResult[] = [];

  // (1) GHL calendar VSL calls ≈ EOD calls_planifies (within 2× tolerance)
  try {
    const rows = await q(`
      WITH cal AS (
        SELECT count(*) n FROM fact_call
        WHERE calendar_id = '8ECqPVcPGz81JGlzCmoG'
          AND status NOT IN ('cancelled')
          AND scheduled_at >= current_date - interval '7 days'
          AND scheduled_at < current_date + interval '1 day'
      ),
      eod AS (
        SELECT COALESCE(sum(calls_planifies), 0) n FROM fact_eod_closeuse
        WHERE submit_date >= current_date - interval '7 days'
      )
      SELECT cal.n cal_n, eod.n eod_n FROM cal, eod
    `);
    const cal = Number(rows[0]?.cal_n ?? 0);
    const eod = Number(rows[0]?.eod_n ?? 0);
    let status: CheckStatus = "green";
    let notes = "";
    if (eod === 0 && cal > 0) {
      status = "yellow";
      notes = "EOD missing — closeuses haven't logged";
    } else if (cal > 0 && eod > 0 && (eod / cal > 3 || cal / eod > 3)) {
      status = "yellow";
      notes = "Calendar vs EOD mismatch >3×";
    }
    out.push({
      check_name: "coherence:calendar_vs_eod_calls",
      status,
      expected: "calendar VSL calls 7d ≈ EOD calls_planifies 7d",
      observed: `calendar=${cal}, eod=${eod}`,
      notes: notes || undefined,
    });
  } catch (e: any) {
    out.push({
      check_name: "coherence:calendar_vs_eod_calls",
      status: "red",
      expected: "queryable",
      observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
    });
  }

  // (2) Whop paid amount ≤ EOD cash_collecte (Whop is subset of total cash)
  try {
    const rows = await q(`
      WITH whop AS (
        SELECT COALESCE(sum(amount), 0) total FROM fact_payment
        WHERE source = 'whop' AND status = 'paid'
          AND paid_at >= current_date - interval '30 days'
      ),
      eod AS (
        SELECT COALESCE(sum(cash_collecte), 0) total FROM fact_eod_closeuse
        WHERE submit_date >= current_date - interval '30 days'
      )
      SELECT whop.total whop_n, eod.total eod_n FROM whop, eod
    `);
    const whop = Number(rows[0]?.whop_n ?? 0);
    const eod = Number(rows[0]?.eod_n ?? 0);
    let status: CheckStatus = "green";
    let notes = "";
    if (whop > eod * 1.05) {
      // Whop card > total EOD declared — suspicious (closeuses under-reporting cash)
      status = "yellow";
      notes = "Whop card payments > EOD declared cash (closeuses under-reporting?)";
    }
    out.push({
      check_name: "coherence:whop_vs_eod_cash",
      status,
      expected: "Whop paid 30d ≤ EOD cash_collecte 30d (Whop is subset)",
      observed: `whop=${whop.toFixed(0)}€, eod=${eod.toFixed(0)}€`,
      notes: notes || undefined,
    });
  } catch (e: any) {
    out.push({
      check_name: "coherence:whop_vs_eod_cash",
      status: "red",
      expected: "queryable",
      observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
    });
  }

  // (3) fact_sale Gagné count vs EOD ventes — checked on BOTH 7j (sensitive) AND 30j (smoothed)
  for (const win of [7, 30] as const) {
    try {
      const rows = await q(`
        WITH ghl AS (
          SELECT count(*) n FROM fact_sale
          WHERE is_won = true AND created_at >= current_date - interval '${win} days'
        ),
        eod AS (
          SELECT COALESCE(sum(ventes_setting + ventes_vsl), 0) n FROM fact_eod_closeuse
          WHERE submit_date >= current_date - interval '${win} days'
            AND NOT (calls_planifies > 0 AND calls_planifies = calls_recus
                     AND calls_planifies = ventes_setting AND calls_planifies = ventes_vsl
                     AND calls_planifies::numeric = cash_contracte)
        )
        SELECT ghl.n ghl_n, eod.n eod_n FROM ghl, eod
      `);
      const ghl = Number(rows[0]?.ghl_n ?? 0);
      const eod = Number(rows[0]?.eod_n ?? 0);
      let status: CheckStatus = "green";
      let notes = "";
      const gap = Math.abs(ghl - eod);
      const tolerance = Math.max(2, Math.max(ghl, eod) * 0.3);
      if (gap > tolerance) {
        // 7d window: gap suggests closeuses not updating pipeline → yellow
        // 30d window: persistent gap → red (confirms systemic process gap)
        status = win === 30 ? "red" : "yellow";
        notes =
          eod > ghl
            ? `${gap} ventes EOD non reflétées en GHL pipeline (closeuses oublient de move l'opp en "Gagné")`
            : `${gap} GHL won sans EOD (closeuses oublient l'EOD ?)`;
      }
      out.push({
        check_name: `coherence:ghl_won_vs_eod_sales_${win}d`,
        status,
        expected: `GHL Gagné ${win}d ≈ EOD ventes ${win}d (within 30%)`,
        observed: `ghl_won=${ghl}, eod_sales=${eod}`,
        notes: notes || undefined,
      });
    } catch (e: any) {
      out.push({
        check_name: `coherence:ghl_won_vs_eod_sales_${win}d`,
        status: "red",
        expected: "queryable",
        observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
      });
    }
  }

  // (4a) Sentinel/test EOD detection — same value repeated across all numeric fields
  // (e.g., test Typeform with 42 everywhere). These corrupt aggregates.
  try {
    const rows = await q(`
      SELECT id, network_id, closer_name, submit_date, calls_planifies, calls_recus,
             ventes_setting, ventes_vsl, cash_contracte
      FROM fact_eod_closeuse
      WHERE submit_date >= current_date - interval '30 days'
        AND calls_planifies > 0
        AND calls_planifies = calls_recus
        AND calls_planifies = ventes_setting
        AND calls_planifies = ventes_vsl
        AND calls_planifies::numeric = cash_contracte
      LIMIT 5
    `);
    if (rows.length > 0) {
      const ids = rows.map((r) => r.id).join(", ");
      const closers = [...new Set(rows.map((r) => r.closer_name))].join(", ");
      out.push({
        check_name: "integrity:eod_sentinel_rows",
        status: "yellow",
        expected: "0 EOD rows with all-equal numeric fields (test sentinel pattern)",
        observed: `${rows.length} ligne(s) suspectes (ids ${ids}) closeuse=${closers}`,
        notes: "Probable test webhook Typeform — supprimer ces lignes pour pas polluer les briefs",
      });
    }
  } catch (e: any) {
    // Non-blocking
  }

  // (4b) Critical NULLs check
  try {
    const rows = await q(`
      SELECT
        (SELECT count(*) FROM fact_sale WHERE stage_name IS NULL) AS null_stage,
        (SELECT count(*) FROM dim_lead WHERE lead_id IS NULL OR lead_id = '') AS null_lead,
        (SELECT count(*) FROM fact_contact WHERE lead_id IS NULL) AS null_contact_lead
    `);
    const r = rows[0] || {};
    const nullStage = Number(r.null_stage ?? 0);
    const nullLead = Number(r.null_lead ?? 0);
    const nullContactLead = Number(r.null_contact_lead ?? 0);
    const total = nullStage + nullLead + nullContactLead;
    out.push({
      check_name: "integrity:critical_nulls",
      status: total > 0 ? "yellow" : "green",
      expected: "0 NULL critical fields",
      observed: `stage=${nullStage}, lead_id=${nullLead}, contact.lead_id=${nullContactLead}`,
    });
  } catch (e: any) {
    out.push({
      check_name: "integrity:critical_nulls",
      status: "red",
      expected: "queryable",
      observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
    });
  }

  return out;
}

// ============================================================================
// CAPACITY — calendar saturation per closeuse
// ============================================================================
async function checkCapacity(): Promise<CheckResult[]> {
  const out: CheckResult[] = [];
  try {
    // Lea-specific: les 2 calendars (VSL + Standard) partagent la même closeuse
    // (Anaïs `8MJYvMAYOFpD`). Quand l'API GHL retourne 7 slots libres sur les 2,
    // c'est la même slot dédupliquée — pas 14. On prend MAX(slots_free) par jour.
    // Les bookings (slots_booked) restent SUM car chaque RDV est unique à un calendar.
    const rows = await q(`
      WITH latest AS (
        SELECT DISTINCT ON (calendar_id, target_date)
          calendar_id, target_date, slots_free, slots_booked
        FROM fact_calendar_capacity
        WHERE target_date >= current_date AND target_date < current_date + interval '4 days'
        ORDER BY calendar_id, target_date, snapshot_at DESC
      ),
      per_day AS (
        SELECT target_date,
               MAX(slots_free)::int AS slots_free,   -- slots dispos partagés = MAX
               SUM(slots_booked)::int AS slots_booked -- bookings uniques = SUM
        FROM latest
        GROUP BY target_date
      )
      SELECT 'closeuses (Anaïs)' AS calendar_name,
             SUM(slots_free + slots_booked)::int AS total,
             SUM(slots_booked)::int AS booked,
             SUM(slots_free)::int AS free,
             ROUND(100.0 * SUM(slots_booked) / NULLIF(SUM(slots_free + slots_booked), 0), 1) AS util_pct
      FROM per_day
    `);
    if (!rows.length) {
      out.push({
        check_name: "capacity:closeuse_72h",
        status: "yellow",
        expected: "fact_calendar_capacity populated",
        observed: "no recent snapshot",
        notes: "Run pipelines/pull_calendar_capacity.py",
      });
      return out;
    }
    for (const r of rows) {
      const util = Number(r.util_pct ?? 0);
      const total = Number(r.total ?? 0);
      const booked = Number(r.booked ?? 0);
      const free = Number(r.free ?? 0);
      let status: CheckStatus = "green";
      let notes = "";
      if (total === 0) {
        status = "yellow";
        notes = "Aucun slot ouvert sur 72h — calendrier fermé ou config absente";
      } else if (util > 90) {
        status = "red";
        notes = "Saturation > 90% — sales constrained, recruter ou élargir capacity";
      } else if (util > 85) {
        status = "yellow";
        notes = "Tension capacity — anticiper recrutement";
      } else if (util < 50 && total >= 5) {
        status = "yellow";
        notes = "Sous 50% utilization — lead-constrained, scaler les ads ou améliorer qualif";
      }
      // Optimal range 70-85% = green
      out.push({
        check_name: `capacity:${r.calendar_name?.slice(0, 30) || "?"}`,
        status,
        expected: "70-85% utilization sur 72h prochaines (optimal)",
        observed: `${booked}/${total} bookés (${util}%) · ${free} libres`,
        delta_pct: util,
        notes: notes || undefined,
      });
    }
  } catch (e: any) {
    out.push({
      check_name: "capacity:closeuse_72h",
      status: "red",
      expected: "queryable",
      observed: `error: ${String(e?.message ?? e).slice(0, 100)}`,
    });
  }
  return out;
}

// ============================================================================
// MAIN
// ============================================================================
export type ValidatorRunResult = {
  ran_at: string;
  total: number;
  green: number;
  yellow: number;
  red: number;
  results: CheckResult[];
  overall_status: CheckStatus;
  blocking: boolean;
};

export async function runValidator(): Promise<ValidatorRunResult> {
  const ranAt = new Date().toISOString();
  const all: CheckResult[] = [];
  for (const fn of [checkFreshness, checkVolume, checkCoherence, checkCapacity]) {
    try {
      all.push(...(await fn()));
    } catch (e: any) {
      all.push({
        check_name: `${fn.name}:fatal`,
        status: "red",
        expected: "ran successfully",
        observed: String(e?.message ?? e).slice(0, 200),
      });
    }
  }

  const green = all.filter((c) => c.status === "green").length;
  const yellow = all.filter((c) => c.status === "yellow").length;
  const red = all.filter((c) => c.status === "red").length;
  const overall: CheckStatus = red > 0 ? "red" : yellow > 0 ? "yellow" : "green";
  const blocking = red > 0;

  // Persist to data_health
  await sb()
    .from("data_health")
    .insert(
      all.map((c) => ({
        check_name: c.check_name,
        status: c.status,
        expected: c.expected,
        observed: c.observed,
        delta_pct: c.delta_pct ?? null,
        notes: c.notes ?? null,
      })),
    );

  // Slack ping if red
  if (red > 0 && process.env.SLACK_WEBHOOK_URL) {
    const reds = all.filter((c) => c.status === "red");
    const blocks = [
      {
        type: "header",
        text: { type: "plain_text", text: `🚨 Data Health: ${red} check(s) RED`, emoji: true },
      },
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: reds
            .map(
              (c) =>
                `• *${c.check_name}*\n  expected: ${c.expected}\n  observed: ${c.observed}${c.notes ? `\n  ${c.notes}` : ""}`,
            )
            .join("\n\n"),
        },
      },
      {
        type: "context",
        elements: [
          {
            type: "mrkdwn",
            text: `Validator · ${green}🟢 ${yellow}🟠 ${red}🔴 · ${new Date().toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}`,
          },
        ],
      },
    ];
    await fetch(process.env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blocks, text: `Data Health: ${red} red` }),
    }).catch((e) => console.error("Slack push failed", e));
  }

  return {
    ran_at: ranAt,
    total: all.length,
    green,
    yellow,
    red,
    results: all,
    overall_status: overall,
    blocking,
  };
}
