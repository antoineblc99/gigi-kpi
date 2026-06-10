// Supabase Edge Function — decision-act
//
// Approve/reject a proposed decision in decision_log (human-in-the-loop).
// Called by Hermes/WhatsApp bridge or curl — NOT by the cockpit (it only displays).
//
// POST { decision_id: number, action: "approve" | "reject", actor: string, reason?: string }
// Header: X-Decision-Secret (must match env DECISION_ACT_SECRET)
//
// IMPORTANT — no real execution here. Approving a decision only flips its status
// in decision_log. The actual Meta/GHL execution is the M1 agents phase, not
// active yet. The response says so explicitly.
//
// decision_log columns: id, agent_name, decision_type, payload (jsonb),
// executed_by, status, created_at, outcome (jsonb).

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

interface ActRequest {
  decision_id?: number;
  action?: string;
  actor?: string;
  reason?: string;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);

  const secret = Deno.env.get("DECISION_ACT_SECRET");
  if (!secret || req.headers.get("x-decision-secret") !== secret) {
    return json({ error: "Unauthorized" }, 401);
  }

  let body: ActRequest;
  try {
    body = await req.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400);
  }

  const { decision_id, action, actor, reason } = body;
  if (!decision_id || typeof decision_id !== "number") {
    return json({ error: "decision_id (number) is required" }, 400);
  }
  if (action !== "approve" && action !== "reject") {
    return json({ error: "action must be 'approve' or 'reject'" }, 400);
  }
  if (!actor || !String(actor).trim()) {
    return json({ error: "actor is required" }, 400);
  }

  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );

  const { data: decision, error: fetchErr } = await sb
    .from("decision_log")
    .select("*")
    .eq("id", decision_id)
    .maybeSingle();

  if (fetchErr) return json({ error: `fetch failed: ${fetchErr.message}` }, 500);
  if (!decision) return json({ error: `decision ${decision_id} not found` }, 404);
  if (decision.status !== "proposed") {
    return json(
      { error: `decision ${decision_id} is '${decision.status}', only 'proposed' can be acted on` },
      409,
    );
  }

  const newStatus = action === "approve" ? "approved" : "rejected";
  const actedAt = new Date().toISOString();
  const outcome = {
    ...(decision.outcome ?? {}),
    action,
    actor: String(actor).trim(),
    reason: reason ?? null,
    acted_at: actedAt,
    executed: false,
    execution_note:
      "Aucune exécution réelle — l'exécution Meta/GHL arrive en phase agents M1. Statut mis à jour uniquement.",
  };

  const { data: updated, error: updateErr } = await sb
    .from("decision_log")
    .update({ status: newStatus, executed_by: String(actor).trim(), outcome })
    .eq("id", decision_id)
    .eq("status", "proposed") // guard against concurrent acts
    .select("*")
    .maybeSingle();

  if (updateErr) return json({ error: `update failed: ${updateErr.message}` }, 500);
  if (!updated) {
    return json({ error: `decision ${decision_id} was acted on concurrently` }, 409);
  }

  return json({
    ok: true,
    executed: false,
    note: "Décision enregistrée. Aucune action Meta/GHL exécutée (phase agents M1 pas encore active).",
    decision: {
      id: updated.id,
      agent_name: updated.agent_name,
      decision_type: updated.decision_type,
      status: updated.status,
      executed_by: updated.executed_by,
      payload: updated.payload,
      outcome: updated.outcome,
      created_at: updated.created_at,
    },
  });
});
