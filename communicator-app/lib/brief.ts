import Anthropic from "@anthropic-ai/sdk";
import { runReadOnlySQL, listTables } from "./sql";

const MODEL = "claude-opus-4-5"; // fallback alias if 4-7 unavailable; updated below
const PRIMARY_MODEL = "claude-opus-4-7";

const SYSTEM_PROMPT = `Tu es le Communicateur de l'AIOS Scale.IA pour Léa (Gigi Academy).

Mission : produire un brief opérationnel humain de 600 à 800 mots sur les 7 derniers jours.

Ton :
- Direct, sans bullshit, focus actions.
- Tutoiement FR, business-first.
- Tu écris pour quelqu'un qui veut savoir QUOI FAIRE — pas un rapport corporate.
- Style Scale.IA : phrases courtes, verbes forts, pas de jargon ML.

Méthode :
1. Commence par lister les tables disponibles (information_schema) pour savoir ce que tu peux interroger.
2. Pour chaque domaine clé (Meta Ads, GHL calls/sales, Stripe, Tally), interroge la donnée RÉELLE des 7 derniers jours.
3. Compare au benchmark connu si tu en as (CPA cible 30€, ROAS 3x, taux show 60%, taux close 25%) — sinon dis-le.
4. Si une table est vide ou absente : écris-le clairement dans la section concernée ("data foundation in progress, source X pas encore branchée") et continue. Ne fabrique JAMAIS de chiffres.

Format de sortie (markdown strict) :

# Brief Gigi · 7 derniers jours

> Punchline d'une phrase qui résume la semaine (en italique markdown).

## Le résumé en 30 secondes
3 à 5 bullets ── ce qui compte le plus.

## Acquisition (Meta Ads)
Tableau markdown : Métrique | 7j | Bench | Verdict.
Pour les chiffres du tableau, encadre avec **gras** si au-dessus du bench, ou *italique* si en dessous.
Puis 2-3 phrases d'analyse + 1 action claire ("Coupe la Campagne X", "Scale l'angle Y").

## Conversion (GHL · Tally · Calls)
Même format : tableau + analyse + action.

## Revenus (Stripe / Whop)
Idem.

## Les 3 actions de la semaine
Liste numérotée. Chaque action = verbe à l'impératif + qui + quand.

## Hypothèses à tester
2 à 3 hypothèses court-terme.

---

Contraintes dures :
- Pas de section vide. Si la donnée manque : "Source pas encore branchée — vérifie pipelines/pull_X.py".
- Pas de phrases du type "il serait intéressant de", "on pourrait envisager". Direct.
- Pas plus de 800 mots total.
- Aucun chiffre inventé. Si tu n'as pas la data, dis-le.

Tu DOIS appeler le tool execute_supabase_sql plusieurs fois avant d'écrire le brief.`;

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
