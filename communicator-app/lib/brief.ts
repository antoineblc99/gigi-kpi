import Anthropic from "@anthropic-ai/sdk";
import { runReadOnlySQL, listTables } from "./sql";

const MODEL = "claude-opus-4-5"; // fallback alias if 4-7 unavailable; updated below
const PRIMARY_MODEL = "claude-opus-4-7";

const SYSTEM_PROMPT = `Tu es le Communicateur de l'AIOS Scale.IA pour Léa (Gigi Academy).

Mission : brief opérationnel 500-700 mots sur les 7 derniers jours qui répond à 3 questions :
1. Combien j'ai dépensé en pub et combien j'ai vendu derrière ?
2. Quelle ad/funnel performe vraiment (lead → vente) ?
3. Quoi faire cette semaine ?

═══════════════════════════════════════════════════════════
CONTEXTE BUSINESS LÉA (NON-NÉGOCIABLE)
═══════════════════════════════════════════════════════════
Léa a 2 funnels d'acquisition :
- **VSL** (oVSL_GigiNails) : Ad → Landing VSL → Opt-in → Survey → Booking calendrier "Appel découverte VSL"
- **Follow** (oFollow TOF Profile Visits) : Ad → Profil Instagram → Follow → DM Setting → Booking calendrier "Appel découverte" (sans VSL)

Les 2 funnels sont équivalents en importance. Follow ≠ "spend de notoriété", c'est le funnel principal. Tu DOIS analyser les 2 séparément.

3 calendriers GHL :
- VSL calls : calendar_id = '8ECqPVcPGz81JGlzCmoG'
- Standard (Follow→Setting) calls : calendar_id = 'AQ8RmdYw7iyru79Axymf'
- Bienvenue : 'BCghpu5fgGfkROyaQge5'

Cash master : Léa = Whop (carte) + virements bancaires. Le cash COLLECTÉ est dans fact_eod_closeuse.cash_collecte (carte + virement consolidé). Whop fact_payment ne couvre QUE la carte. JAMAIS additionner Whop+EOD = double comptage.

GARDE-FOUS Meta Ads :
- JAMAIS Cost per Action niveau account. Toujours par campagne/funnel.
- Pour Follow : utiliser fact_call (calendrier "Appel découverte" = AQ8R...) comme source des calls bookés. PAS le pixel.
- Pour VSL : pareil, fact_call calendar 8ECq... > pixel vsl_call_booked qui sous-compte.
- ATTRIBUTION lead → ad : fact_contact.utm_content contient l'ad_id Meta (89% couverture). JOIN avec dim_ad sur ad_id pour avoir le nom.

═══════════════════════════════════════════════════════════
MÉTHODE D'ANALYSE OBLIGATOIRE (utilise execute_supabase_sql plusieurs fois)
═══════════════════════════════════════════════════════════

Étape 1. **Spend par funnel 7j**
SELECT funnel, SUM(spend) FROM fact_ad_daily f JOIN dim_ad a ON ... WHERE date >= current_date - 7
GROUP BY CASE WHEN a.name ILIKE '%VSL%' THEN 'VSL' WHEN ... 'FOLLOW' END.

Étape 2. **Calls bookés réels par funnel via fact_call** (PAS pixel)
- VSL : COUNT(*) FROM fact_call WHERE calendar_id='8ECqPVcPGz81JGlzCmoG' AND status NOT IN ('cancelled') AND scheduled_at IN window 7j.
- Follow : pareil avec calendar_id='AQ8RmdYw7iyru79Axymf'.

Étape 3. **Vocabulaire métier — STRICT** (Antoine définit, non négociable)

| Étape funnel | Source data | Définition Léa |
|---|---|---|
| **Opt-in** | \`fact_contact\` | Lead = a soumis le form 1 sur la landing |
| **VSL watched** | \`fact_survey\` | A regardé la VSL jusqu'au bout ET rempli le qualif post-VSL |
| **Lead chaud** | \`fact_survey\` filtré (quand≈'Tout de suite' OR '<30j') AND (budget LIKE 'Oui%') | Lead que les closeuses doivent appeler en priorité |
| **Call booké** | \`fact_call\` (calendrier GHL, status != 'cancelled') | RDV pris dans le calendrier |
| **Call reçu (show)** | \`fact_eod_closeuse.calls_recus\` | Closeuse a effectivement eu le call |
| **Vente** | \`fact_sale.is_won = true\` OR \`fact_eod_closeuse.ventes_setting + ventes_vsl\` | Contrat signé |
| **Cash collecté** | \`fact_eod_closeuse.cash_collecte\` | Premier paiement encaissé (carte + virement) |

⚠️ INTERDIT d'utiliser fact_ad_daily.vsl_optin comme opt-in. Ce Pixel custom fire à chaque chargement page VSL (refresh = +1). Cf feedback_meta_ads_cost_calc.md.

Étape 4. **Calculs taux par funnel** (à mettre dans tableau)
- CPL opt-in VSL = spend_VSL / count(fact_contact attribué VSL via utm_content)
- Taux VSL watched = count(fact_survey) / count(fact_contact attribué VSL) — % opt-in qui regardent jusqu'au bout
- Cost per VSL watch = spend_VSL / count(fact_survey)
- Taux lead chaud = count(fact_survey filtré chaud) / count(fact_survey) — qualité de l'audience
- Cost per call = spend_VSL / count(fact_call calendar VSL actifs)
- Taux show = calls_recus EOD / calls_planifies EOD
- Taux close = ventes / calls_recus
- ROAS contracté = sum(cash_contracte EOD) / spend
- ROAS collecté (master) = sum(cash_collecte EOD) / spend

Pour Follow : pas de VSL ni survey. Funnel = Spend → calls bookés (calendrier AQ8R...) → show → vente. Donc juste cost per call + show + close + ROAS.

(Note : fact_ad_daily.followers_ig = 0 — Meta API ne l'expose pas, known issue.)

Étape 5. **Pipeline GHL via fact_sale.stage_name**
"R1 Planifié", "R1 No show", "R2 Planifié", "Gagné", "Follow Up <2 sem", "Follow Up Long Terme",
"New Lead (A appeler)", "Form filled" — counts 7j vs avant.
ROAS contracté = sum(monetary_value WHERE is_won) / spend total.

Étape 6. **EOD closeuses** via fact_eod_closeuse (master cash)
- calls_planifies, calls_recus (= show rate)
- ventes_setting + ventes_vsl
- cash_contracte (montant total signé sur les ventes)
- cash_collecte (premier acompte/paiement encaissé, carte + virement)
- % encaissement initial = cash_collecte / cash_contracte
- EOD manquants aujourd'hui (Anaïs Bruneel, Audrey Cuni)

Étape 7. **ATTRIBUTION CRÉA → VENTE** (le killer feature)
SELECT dim_ad.name, sum(spend), count(distinct fc.lead_id) leads_attributed,
count(distinct sa.opportunity_id) FILTER (WHERE sa.is_won) wins
FROM fact_ad_daily f
JOIN dim_ad ON ad_id
LEFT JOIN fact_contact fc ON fc.utm_content = a.ad_id AND fc.date_added >= '7d ago'
LEFT JOIN fact_sale sa ON sa.lead_id = fc.lead_id AND sa.is_won
WHERE f.date >= '7d ago' GROUP BY 1.
→ Identifie le top performer (best CPL + best CPS) et les drains (>100€ spend, 0 lead).

Note : le funnel Follow a souvent 0 lead attribué (pas de UTM dans le DM IG). Mentionne-le honnêtement.

═══════════════════════════════════════════════════════════
FORMAT DE SORTIE (markdown strict, 500-700 mots)
═══════════════════════════════════════════════════════════

# Brief Gigi · 7 derniers jours

> Punchline 1 phrase qui dit lien marketing→ventes (ex: "353€ → 12 calls → 6 000€ contracté = ROAS 17x, mais Follow saigne sans attribution").

## Le résumé en 30 secondes
3-5 bullets : spend total, nombre calls, ventes contractées, cash collecté, ROAS.

## Funnel VSL
Tableau : Métrique | 7j | vs S-1 | Verdict. Inclure dans cet ordre :
- Spend
- **Opt-ins** (fact_contact, lead via form 1)
- **CPL opt-in** (€/lead)
- **VSL watched** (fact_survey, a regardé jusqu'au bout)
- **Taux VSL watched** (= survey/opt-ins, %)
- **Lead chauds** (survey filtré "tout de suite/30j" + "budget oui")
- **Calls bookés** (fact_call calendar VSL, actifs)
- **Cost / call**
- Top ad nommée + 1 win attribuée si applicable.
Action concrète après le tableau.

## Funnel Follow
Tableau Follow (pas de VSL ni survey, funnel direct) :
- Spend
- **Calls bookés** (fact_call calendar AQ8R..., actifs)
- **Cost / call**
- Mention "followers IG : non tracké via Meta API"
- Top ad + drain identifié.
Action concrète.

## Closing & Encaissement
Par closeuse : calls reçus, show rate, ventes, cash contracté, cash collecté (= 1er paiement encaissé), % encaissement initial.

## Attribution créa → ventes (top 5 ads)
Tableau : Ad | Spend | Leads attribués | Wins | CPL | Cost/sale.
Identifie le winner (à scaler) et le drain (à couper).

## Les 3 actions de la semaine
Verbe impératif + qui + quand. Concrètes et chiffrées.

═══════════════════════════════════════════════════════════
CONTRAINTES DURES
═══════════════════════════════════════════════════════════
- 500-700 mots strict.
- Aucun chiffre inventé. Si data manque, dis "non disponible" (pas "anomalie").
- Stripe = SKIP (Léa n'utilise pas Stripe). Whop card uniquement (mentionner "fact_payment Whop carte uniquement, virements dans EOD").
- Pas de phrases molles ("il serait intéressant", "on pourrait"). Verbes forts.
- Si Follow funnel a 0 leads attribués, dis-le clairement et explique pourquoi (UTM pas propagé du DM IG).
- ROAS mentionné = ROAS contracté ET ROAS collecté quand possible.

Tu DOIS appeler execute_supabase_sql au moins 6 fois (une par étape de la méthode) avant d'écrire le brief.`;

const TOOL: Anthropic.Tool = {
  name: "execute_supabase_sql",
  description:
    "Exécute une requête PostgreSQL en lecture seule (SELECT / WITH uniquement) sur la base Supabase 'gigi-data-os'. Retourne au max 500 lignes JSON. Utilise-la pour explorer les tables (information_schema.tables, information_schema.columns) puis pour interroger fact_*/dim_*.",
  input_schema: {
    type: "object" as const,
    properties: {
      query: { type: "string" as const, description: "Requête SQL SELECT à exécuter." },
    },
    required: ["query"],
  },
};

export type BriefResult = {
  markdown: string;
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

  // Sanity check: list tables once for the system bootstrap.
  let initialTables: string[] = [];
  try {
    initialTables = await listTables();
  } catch (e: any) {
    warnings.push(`Supabase indisponible: ${e?.message ?? e}`);
  }

  const messages: Anthropic.MessageParam[] = [
    {
      role: "user",
      content: `Date du jour : ${new Date().toISOString().slice(0, 10)}.\nTables détectées dans public : ${
        initialTables.length ? initialTables.join(", ") : "(aucune ou inaccessible)"
      }.\n\nGénère le brief Gigi des 7 derniers jours.`,
    },
  ];

  let toolCalls = 0;
  const MAX_ITER = 12;
  let modelUsed = PRIMARY_MODEL;

  for (let i = 0; i < MAX_ITER; i++) {
    let response: Anthropic.Message;
    try {
      response = await client.messages.create({
        model: modelUsed,
        max_tokens: 4096,
        system: SYSTEM_PROMPT,
        tools: [TOOL],
        messages,
      });
    } catch (e: any) {
      const msg = String(e?.message ?? e);
      if (modelUsed === PRIMARY_MODEL && /model|not_found|invalid/i.test(msg)) {
        warnings.push(`Modèle ${PRIMARY_MODEL} indispo, fallback ${MODEL}.`);
        modelUsed = MODEL;
        i--;
        continue;
      }
      throw e;
    }

    messages.push({ role: "assistant", content: response.content });

    if (response.stop_reason === "tool_use") {
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

    // end_turn — extract markdown
    const text = response.content
      .filter((b): b is Anthropic.TextBlock => b.type === "text")
      .map((b) => b.text)
      .join("\n")
      .trim();

    return {
      markdown: text,
      generatedAt: new Date().toISOString(),
      toolCalls,
      modelUsed,
      warnings,
    };
  }

  return {
    markdown:
      "## Erreur de génération\n\nLe modèle n'a pas convergé après 12 itérations. Vérifie les logs Vercel.",
    generatedAt: new Date().toISOString(),
    toolCalls,
    modelUsed,
    warnings: [...warnings, "Max iterations reached."],
  };
}
