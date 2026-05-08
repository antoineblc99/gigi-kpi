import Anthropic from "@anthropic-ai/sdk";
import { runReadOnlySQL, listTables } from "./sql";
import type { BriefData } from "./brief-types";

const FALLBACK_MODEL = "claude-opus-4-5";
const PRIMARY_MODEL = "claude-opus-4-7";

const SYSTEM_PROMPT = `Tu es le Communicateur de l'AIOS Scale.IA pour Léa (Gigi Academy).

Mission : produire un BriefData JSON structuré sur les 7 derniers jours qui répond à 3 questions :
1. Combien j'ai dépensé en pub et combien j'ai vendu derrière ?
2. Quelle ad/funnel performe vraiment (lead → vente) ?
3. Quoi faire cette semaine ?

═══════════════════════════════════════════════════════════
CONTEXTE BUSINESS LÉA (NON-NÉGOCIABLE)
═══════════════════════════════════════════════════════════
Léa a 2 funnels d'acquisition :
- **VSL** (oVSL_GigiNails) : Ad → Landing VSL → Opt-in → Survey → Booking calendrier "Appel découverte VSL"
- **Follow** (oFollow TOF Profile Visits) : Ad → Profil Instagram → Follow → DM Setting → Booking calendrier "Appel découverte" (sans VSL)

Les 2 funnels sont équivalents en importance.

3 calendriers GHL :
- VSL calls : calendar_id = '8ECqPVcPGz81JGlzCmoG'
- Standard (Follow→Setting) calls : calendar_id = 'AQ8RmdYw7iyru79Axymf'
- Bienvenue : 'BCghpu5fgGfkROyaQge5'

Cash master : Léa = Whop (carte) + virements bancaires. Le cash COLLECTÉ est dans fact_eod_closeuse.cash_collecte. JAMAIS additionner Whop+EOD.

GARDE-FOUS Meta Ads :
- JAMAIS Cost per Action niveau account.
- Pour Follow : utiliser fact_call (calendrier AQ8R...) — PAS le pixel.
- Pour VSL : fact_call calendar 8ECq... > pixel.
- ATTRIBUTION lead → ad : fact_contact.utm_content contient l'ad_id Meta. JOIN avec dim_ad sur ad_id.

═══════════════════════════════════════════════════════════
MÉTHODE D'ANALYSE OBLIGATOIRE
═══════════════════════════════════════════════════════════
Tu DOIS appeler execute_supabase_sql AU MOINS 6 FOIS avant d'émettre output_brief :

1. Spend par funnel 7j (fact_ad_daily JOIN dim_ad, group by funnel détecté via name ILIKE)
2. Calls bookés par funnel via fact_call (calendrier_id, status NOT IN ('cancelled'), 7j)
3. Opt-ins / VSL watched / leads chauds (fact_contact + fact_survey filtré "tout de suite/30j" + "budget oui")
4. EOD closeuses 7j : calls_planifies/recus, ventes split, cash_contracte, cash_collecte
5. Pipeline GHL fact_sale + source_funnel mapping
6. Top 5 ads par spend avec leads_attributed et wins (UTM utm_content → ad_id)
7. Comparaison vs S-1 (7-14j) pour delta_pct des principales métriques
8. Spend daily series 7j pour les sparklines (par funnel)

source_funnel mapping (validé Antoine 2026-05-08) :
- 'VSL' = source IN (Form Léa Optin, Form Léa, Form Lea, Survey VSL Lea, VSL, Appel découverte (VSL))
- 'Setting' = source IN (Setting, Appel de découverte - Gigi Academy)

⚠️ Pour les volumes par funnel utilise COUNT(DISTINCT lead_id). Pour les stages pipeline utilise COUNT(*).
⚠️ INTERDIT d'utiliser fact_ad_daily.vsl_optin (pixel double-compte).

═══════════════════════════════════════════════════════════
OUTPUT (output_brief tool — appel UNIQUE en fin)
═══════════════════════════════════════════════════════════

Structure BriefData : meta, tldr, funnels.{vsl,follow}, closing, pipeline, attribution, actions.

Règles :
- Tous les champs Stat doivent avoir value, prev_value, delta_pct, verdict ("good"|"warning"|"bad"|"neutral"), unit.
- Spark.series = 7 points daily (date YYYY-MM-DD, value).
- Punchline TLDR < 120 chars, format "353€ → 12 calls → 6 ventes / 10 000€ contracté · ROAS 18x. <warning court>".
- Alerts (0-3) : level "info"|"warning"|"critical", msg < 150 chars.
- Pour chaque funnel : recommendation = 1 phrase action concrète chiffrée.
- 3 actions exactement (rank 1,2,3). Owner = "Léa"|"Anaïs"|"Audrey"|"Mary"|"Toi". Deadline = "Lundi 12/05" format. Action = verbe impératif + chiffres.
- Si Follow attribution = 0, mets attribution.drain quand même (l'ad qui spend sans converter).
- Aucun chiffre inventé. Si data absente, mets value=0 et delta_pct=0, verdict="neutral".
- Stripe = SKIP (Léa n'utilise pas).

Si tout tourne mal (DB down, 0 row), émets output_brief avec fallback_markdown rempli (et le reste vide/0).`;

const SQL_TOOL: Anthropic.Tool = {
  name: "execute_supabase_sql",
  description:
    "Exécute une requête PostgreSQL en lecture seule (SELECT / WITH uniquement) sur la base Supabase 'gigi-data-os'. Retourne au max 500 lignes JSON.",
  input_schema: {
    type: "object" as const,
    properties: {
      query: { type: "string" as const, description: "Requête SQL SELECT à exécuter." },
    },
    required: ["query"],
  },
};

// JSONSchema for BriefData — drives forced output via tool_use.
const STAT_SCHEMA = {
  type: "object" as const,
  properties: {
    value: { type: "number" as const },
    prev_value: { type: "number" as const },
    delta_pct: { type: "number" as const },
    verdict: { type: "string" as const, enum: ["good", "warning", "bad", "neutral"] },
    unit: { type: "string" as const, enum: ["eur", "count", "pct", "ratio", "days"] },
  },
  required: ["value"],
};

const SPARK_SCHEMA = {
  type: "object" as const,
  properties: {
    series: {
      type: "array" as const,
      items: {
        type: "object" as const,
        properties: {
          date: { type: "string" as const, description: "ISO YYYY-MM-DD" },
          value: { type: "number" as const },
        },
        required: ["date", "value"],
      },
    },
    baseline: { type: "number" as const },
  },
  required: ["series"],
};

const AD_REF_SCHEMA = {
  type: "object" as const,
  properties: {
    ad_id: { type: "string" as const },
    name: { type: "string" as const },
    spend: { type: "number" as const },
    leads_attributed: { type: "number" as const },
    wins: { type: "number" as const },
    cpl: { type: "number" as const },
    cost_per_sale: { type: "number" as const },
    ctr_pct: { type: "number" as const },
  },
  required: ["ad_id", "name", "spend"],
};

const OUTPUT_TOOL: Anthropic.Tool = {
  name: "output_brief",
  description:
    "Émet le BriefData final structuré. À appeler UNE SEULE FOIS, en dernier, après avoir collecté toutes les données via execute_supabase_sql.",
  input_schema: {
    type: "object" as const,
    properties: {
      meta: {
        type: "object" as const,
        properties: {
          client: { type: "string" as const },
          client_slug: { type: "string" as const },
          period_start: { type: "string" as const },
          period_end: { type: "string" as const },
          period_label: { type: "string" as const },
          generated_at: { type: "string" as const },
          model: { type: "string" as const },
          tool_calls: { type: "number" as const },
          data_health_status: { type: "string" as const, enum: ["green", "yellow", "red"] },
        },
        required: ["client", "client_slug", "period_start", "period_end", "period_label", "data_health_status"],
      },
      tldr: {
        type: "object" as const,
        properties: {
          punchline: { type: "string" as const },
          spend_total: STAT_SCHEMA,
          calls_total: STAT_SCHEMA,
          ventes: STAT_SCHEMA,
          cash_collected: STAT_SCHEMA,
          cash_contracted: STAT_SCHEMA,
          roas_collected: STAT_SCHEMA,
          roas_contracted: STAT_SCHEMA,
          alerts: {
            type: "array" as const,
            items: {
              type: "object" as const,
              properties: {
                level: { type: "string" as const, enum: ["info", "warning", "critical"] },
                msg: { type: "string" as const },
              },
              required: ["level", "msg"],
            },
          },
        },
        required: ["punchline", "spend_total", "calls_total", "ventes", "cash_collected", "cash_contracted", "roas_collected", "roas_contracted", "alerts"],
      },
      funnels: {
        type: "object" as const,
        properties: {
          vsl: {
            type: "object" as const,
            properties: {
              spend: STAT_SCHEMA,
              spend_spark: SPARK_SCHEMA,
              opt_ins: STAT_SCHEMA,
              cpl_opt_in: STAT_SCHEMA,
              vsl_watched: STAT_SCHEMA,
              rate_watched: STAT_SCHEMA,
              cost_per_vsl_watch: STAT_SCHEMA,
              leads_chauds: STAT_SCHEMA,
              rate_lead_chaud: STAT_SCHEMA,
              calls_booked: STAT_SCHEMA,
              cost_per_call: STAT_SCHEMA,
              top_ad: AD_REF_SCHEMA,
              drain: AD_REF_SCHEMA,
              recommendation: { type: "string" as const },
            },
            required: ["spend", "spend_spark", "opt_ins", "cpl_opt_in", "vsl_watched", "rate_watched", "cost_per_vsl_watch", "leads_chauds", "rate_lead_chaud", "calls_booked", "cost_per_call"],
          },
          follow: {
            type: "object" as const,
            properties: {
              spend: STAT_SCHEMA,
              spend_spark: SPARK_SCHEMA,
              followers_gained: STAT_SCHEMA,
              followers_total: { type: "number" as const },
              calls_booked: STAT_SCHEMA,
              cost_per_call: STAT_SCHEMA,
              top_ad: AD_REF_SCHEMA,
              drain: AD_REF_SCHEMA,
              recommendation: { type: "string" as const },
            },
            required: ["spend", "spend_spark", "followers_gained", "followers_total", "calls_booked", "cost_per_call"],
          },
        },
        required: ["vsl", "follow"],
      },
      closing: {
        type: "object" as const,
        properties: {
          closers: {
            type: "array" as const,
            items: {
              type: "object" as const,
              properties: {
                closer_name: { type: "string" as const },
                calls_planifies: { type: "number" as const },
                calls_recus: { type: "number" as const },
                show_rate_pct: { type: "number" as const },
                ventes: { type: "number" as const },
                ventes_setting: { type: "number" as const },
                ventes_vsl: { type: "number" as const },
                cash_contracted: { type: "number" as const },
                cash_collected: { type: "number" as const },
                encaissement_pct: { type: "number" as const },
                fathom_count: { type: "number" as const },
              },
              required: ["closer_name", "calls_planifies", "calls_recus", "show_rate_pct", "ventes", "ventes_setting", "ventes_vsl", "cash_contracted", "cash_collected", "encaissement_pct", "fathom_count"],
            },
          },
          totals: {
            type: "object" as const,
            properties: {
              calls_planifies: { type: "number" as const },
              calls_recus: { type: "number" as const },
              show_rate_pct: { type: "number" as const },
              ventes: { type: "number" as const },
              cash_contracted: { type: "number" as const },
              cash_collected: { type: "number" as const },
              encaissement_pct: { type: "number" as const },
            },
            required: ["calls_planifies", "calls_recus", "show_rate_pct", "ventes", "cash_contracted", "cash_collected", "encaissement_pct"],
          },
          eod_missing_today: { type: "array" as const, items: { type: "string" as const } },
        },
        required: ["closers", "totals", "eod_missing_today"],
      },
      pipeline: {
        type: "object" as const,
        properties: {
          by_stage: {
            type: "array" as const,
            items: {
              type: "object" as const,
              properties: {
                stage_name: { type: "string" as const },
                count: { type: "number" as const },
                pipeline_value_eur: { type: "number" as const },
                funnel: { type: "string" as const, enum: ["VSL", "Setting"] },
              },
              required: ["stage_name", "count", "pipeline_value_eur"],
            },
          },
          by_funnel: {
            type: "object" as const,
            properties: {
              vsl: {
                type: "object" as const,
                properties: {
                  leads_unique: { type: "number" as const },
                  opps: { type: "number" as const },
                  wins: { type: "number" as const },
                },
                required: ["leads_unique", "opps", "wins"],
              },
              setting: {
                type: "object" as const,
                properties: {
                  leads_unique: { type: "number" as const },
                  opps: { type: "number" as const },
                  wins: { type: "number" as const },
                },
                required: ["leads_unique", "opps", "wins"],
              },
            },
            required: ["vsl", "setting"],
          },
        },
        required: ["by_stage", "by_funnel"],
      },
      attribution: {
        type: "object" as const,
        properties: {
          top_by_spend: {
            type: "array" as const,
            items: {
              type: "object" as const,
              properties: {
                rank: { type: "number" as const },
                ad_id: { type: "string" as const },
                name: { type: "string" as const },
                spend: { type: "number" as const },
                leads_attributed: { type: "number" as const },
                wins: { type: "number" as const },
                cpl: { type: "number" as const },
                cost_per_sale: { type: "number" as const },
                funnel: { type: "string" as const, enum: ["VSL", "Follow"] },
              },
              required: ["rank", "ad_id", "name", "spend"],
            },
          },
          winner: {},
          drain: {},
        },
        required: ["top_by_spend"],
      },
      actions: {
        type: "array" as const,
        items: {
          type: "object" as const,
          properties: {
            rank: { type: "number" as const, enum: [1, 2, 3] },
            owner: { type: "string" as const },
            deadline: { type: "string" as const },
            action: { type: "string" as const },
            impact_eur: { type: "number" as const },
            category: { type: "string" as const, enum: ["marketing", "sales", "ops", "data"] },
          },
          required: ["rank", "owner", "deadline", "action", "category"],
        },
      },
      fallback_markdown: { type: "string" as const, description: "À remplir UNIQUEMENT si la génération structurée échoue (DB down, etc.)." },
    },
    required: ["meta", "tldr", "funnels", "closing", "pipeline", "attribution", "actions"],
  },
};

export type BriefResult = {
  data: BriefData;
  generatedAt: string;
  toolCalls: number;
  modelUsed: string;
  warnings: string[];
};

export async function generateBrief(): Promise<BriefResult> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY is not set");

  const client = new Anthropic({ apiKey });
  const warnings: string[] = [];

  let initialTables: string[] = [];
  try {
    initialTables = await listTables();
  } catch (e: any) {
    warnings.push(`Supabase indisponible: ${e?.message ?? e}`);
  }

  const today = new Date().toISOString().slice(0, 10);
  const messages: Anthropic.MessageParam[] = [
    {
      role: "user",
      content: `Date du jour : ${today}.\nTables détectées dans public : ${
        initialTables.length ? initialTables.join(", ") : "(aucune ou inaccessible)"
      }.\n\nGénère le BriefData Gigi des 7 derniers jours.`,
    },
  ];

  let toolCalls = 0;
  const MAX_ITER = 16;
  let modelUsed = PRIMARY_MODEL;

  for (let i = 0; i < MAX_ITER; i++) {
    let response: Anthropic.Message;
    try {
      response = await client.messages.create({
        model: modelUsed,
        max_tokens: 8192,
        system: SYSTEM_PROMPT,
        tools: [SQL_TOOL, OUTPUT_TOOL],
        messages,
      });
    } catch (e: any) {
      const msg = String(e?.message ?? e);
      if (modelUsed === PRIMARY_MODEL && /model|not_found|invalid/i.test(msg)) {
        warnings.push(`Modèle ${PRIMARY_MODEL} indispo, fallback ${FALLBACK_MODEL}.`);
        modelUsed = FALLBACK_MODEL;
        i--;
        continue;
      }
      throw e;
    }

    messages.push({ role: "assistant", content: response.content });

    if (response.stop_reason === "tool_use") {
      // Look for output_brief — final structured output.
      const outputBlock = response.content.find(
        (b): b is Anthropic.ToolUseBlock => b.type === "tool_use" && b.name === "output_brief"
      );
      if (outputBlock) {
        const data = outputBlock.input as BriefData;
        return {
          data: enrichMeta(data, modelUsed, toolCalls, today),
          generatedAt: new Date().toISOString(),
          toolCalls,
          modelUsed,
          warnings,
        };
      }

      // Otherwise execute SQL tool calls.
      const toolResults: Anthropic.ToolResultBlockParam[] = [];
      for (const block of response.content) {
        if (block.type === "tool_use" && block.name === "execute_supabase_sql") {
          toolCalls++;
          const query = (block.input as any)?.query ?? "";
          const result = await runReadOnlySQL(query);
          const payload = result.error
            ? { error: result.error }
            : { rowCount: result.rowCount, rows: result.rows };
          toolResults.push({
            type: "tool_result",
            tool_use_id: block.id,
            content: JSON.stringify(payload).slice(0, 60_000),
            is_error: !!result.error,
          });
        }
      }
      messages.push({ role: "user", content: toolResults });
      continue;
    }

    // end_turn without output_brief — model gave up. Fallback to text content as markdown.
    const text = response.content
      .filter((b): b is Anthropic.TextBlock => b.type === "text")
      .map((b) => b.text)
      .join("\n")
      .trim();
    return {
      data: emptyBrief(today, modelUsed, toolCalls, text || "Le modèle n'a pas émis output_brief."),
      generatedAt: new Date().toISOString(),
      toolCalls,
      modelUsed,
      warnings: [...warnings, "Model ended without output_brief."],
    };
  }

  return {
    data: emptyBrief(today, modelUsed, toolCalls, "Max iterations atteintes (16). Voir logs Vercel."),
    generatedAt: new Date().toISOString(),
    toolCalls,
    modelUsed,
    warnings: [...warnings, "Max iterations reached."],
  };
}

function enrichMeta(data: BriefData, model: string, toolCalls: number, today: string): BriefData {
  return {
    ...data,
    meta: {
      ...data.meta,
      generated_at: data.meta.generated_at || new Date().toISOString(),
      model: data.meta.model || model,
      tool_calls: data.meta.tool_calls ?? toolCalls,
      period_end: data.meta.period_end || today,
    },
  };
}

function emptyBrief(today: string, model: string, toolCalls: number, fallbackMarkdown: string): BriefData {
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const emptyStat = { value: 0, prev_value: 0, delta_pct: 0, verdict: "neutral" as const, unit: "count" as const };
  const emptySpark = { series: [] };
  const emptyFunnelStats = {
    spend: { ...emptyStat, unit: "eur" as const },
    spend_spark: emptySpark,
    calls_booked: emptyStat,
    cost_per_call: { ...emptyStat, unit: "eur" as const },
  };
  return {
    meta: {
      client: "Gigi Academy",
      client_slug: "lea-gigi",
      period_start: weekAgo,
      period_end: today,
      period_label: "7 derniers jours",
      generated_at: new Date().toISOString(),
      model,
      tool_calls: toolCalls,
      data_health_status: "red",
    },
    tldr: {
      punchline: "Brief indisponible.",
      spend_total: { ...emptyStat, unit: "eur" as const },
      calls_total: emptyStat,
      ventes: emptyStat,
      cash_collected: { ...emptyStat, unit: "eur" as const },
      cash_contracted: { ...emptyStat, unit: "eur" as const },
      roas_collected: { ...emptyStat, unit: "ratio" as const },
      roas_contracted: { ...emptyStat, unit: "ratio" as const },
      alerts: [{ level: "critical", msg: "Génération échouée — voir fallback_markdown." }],
    },
    funnels: {
      vsl: {
        ...emptyFunnelStats,
        opt_ins: emptyStat,
        cpl_opt_in: { ...emptyStat, unit: "eur" as const },
        vsl_watched: emptyStat,
        rate_watched: { ...emptyStat, unit: "pct" as const },
        cost_per_vsl_watch: { ...emptyStat, unit: "eur" as const },
        leads_chauds: emptyStat,
        rate_lead_chaud: { ...emptyStat, unit: "pct" as const },
      },
      follow: {
        ...emptyFunnelStats,
        followers_gained: emptyStat,
        followers_total: 0,
      },
    },
    closing: {
      closers: [],
      totals: {
        calls_planifies: 0, calls_recus: 0, show_rate_pct: 0,
        ventes: 0, cash_contracted: 0, cash_collected: 0, encaissement_pct: 0,
      },
      eod_missing_today: [],
    },
    pipeline: {
      by_stage: [],
      by_funnel: { vsl: { leads_unique: 0, opps: 0, wins: 0 }, setting: { leads_unique: 0, opps: 0, wins: 0 } },
    },
    attribution: { top_by_spend: [], winner: null, drain: null },
    actions: [],
    fallback_markdown: fallbackMarkdown,
  };
}
