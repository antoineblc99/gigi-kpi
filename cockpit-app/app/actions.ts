"use server";

/**
 * Server action — valider/refuser une décision depuis le cockpit (mode opérateur).
 * Même logique de transition que l'Edge Function decision-act :
 * proposed → approved/rejected, guard status=proposed, outcome jsonb mergé.
 * Update via PostgREST direct (le RPC execute_readonly_sql est read-only).
 * Service role server-side uniquement.
 */
import { revalidatePath } from "next/cache";
import { isOperator } from "@/lib/op";

const ACTOR = "antoine (cockpit)";

export async function decideAction(formData: FormData): Promise<void> {
  if (!(await isOperator())) throw new Error("Non autorisé");

  const id = Number(formData.get("id"));
  const action = String(formData.get("action") || "");
  const reasonRaw = String(formData.get("reason") || "").trim();
  if (!Number.isInteger(id) || id <= 0) throw new Error("decision id invalide");
  if (action !== "approve" && action !== "reject") throw new Error("action invalide");

  const url = process.env.SUPABASE_PROJECT_URL || process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("env Supabase manquante");

  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };

  // Outcome existant (l'Edge Function merge, on fait pareil)
  const curRes = await fetch(
    `${url}/rest/v1/decision_log?id=eq.${id}&select=status,outcome`,
    { headers, cache: "no-store" }
  );
  if (!curRes.ok) throw new Error(`fetch decision: HTTP ${curRes.status}`);
  const rows = (await curRes.json()) as { status: string; outcome: Record<string, unknown> | null }[];
  const current = rows[0];
  if (!current || current.status !== "proposed") {
    // déjà actée (concurrence) ou introuvable : on rafraîchit, pas d'erreur bloquante
    revalidatePath("/");
    return;
  }

  const outcome = {
    ...(current.outcome ?? {}),
    action,
    actor: ACTOR,
    reason: reasonRaw || null,
    acted_at: new Date().toISOString(),
    executed: false,
    execution_note:
      "Aucune exécution réelle — l'exécution Meta/GHL arrive en phase agents M1. Statut mis à jour uniquement.",
  };

  const patchRes = await fetch(
    `${url}/rest/v1/decision_log?id=eq.${id}&status=eq.proposed`,
    {
      method: "PATCH",
      headers: { ...headers, Prefer: "return=representation" },
      body: JSON.stringify({
        status: action === "approve" ? "approved" : "rejected",
        executed_by: ACTOR,
        outcome,
      }),
      cache: "no-store",
    }
  );
  if (!patchRes.ok) throw new Error(`update decision: HTTP ${patchRes.status}`);
  const updated = (await patchRes.json()) as unknown[];
  if (!Array.isArray(updated) || updated.length === 0) {
    // guard status=proposed a filtré : actée entre-temps — on rafraîchit simplement
  }

  revalidatePath("/");
}
