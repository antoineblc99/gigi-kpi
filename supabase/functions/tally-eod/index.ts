// Supabase Edge Function — Tally EOD closeuses webhook
//
// Receives a Tally form submission, normalizes fields, upserts into
// fact_eod_closeuse. Idempotent on Tally responseId.
//
// Configure on Tally: Form → Integrations → Webhook → POST URL =
//   https://<project-ref>.supabase.co/functions/v1/tally-eod
//   Header: x-webhook-secret: <TALLY_WEBHOOK_SECRET>
//
// Deploy: supabase functions deploy tally-eod --project-ref <ref>
//
// Env required (set via supabase secrets set):
//   - TALLY_WEBHOOK_SECRET  (shared secret for verification)
//   - SUPABASE_URL          (auto-injected)
//   - SUPABASE_SERVICE_ROLE_KEY (auto-injected)

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

interface TallyField {
  key: string;
  label: string;
  type: string;
  value: any;
}
interface TallyPayload {
  eventType: string;
  data: {
    responseId: string;
    submissionId?: string;
    formId: string;
    formName?: string;
    createdAt: string;
    fields: TallyField[];
  };
}

function num(v: any): number {
  if (v == null || v === "") return 0;
  if (typeof v === "number") return v;
  const n = parseFloat(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

function str(v: any): string | null {
  if (v == null) return null;
  if (Array.isArray(v)) return v.join(", ") || null;
  const s = String(v).trim();
  return s || null;
}

function findField(fields: TallyField[], labelMatcher: RegExp): any {
  const f = fields.find((x) => labelMatcher.test(x.label || ""));
  return f?.value ?? null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const webhookSecret = Deno.env.get("TALLY_WEBHOOK_SECRET");
  if (webhookSecret) {
    const got = req.headers.get("x-webhook-secret") || req.headers.get("tally-signature");
    if (got !== webhookSecret) {
      return new Response("Unauthorized", { status: 401 });
    }
  }

  let payload: TallyPayload;
  try {
    payload = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  if (payload.eventType !== "FORM_RESPONSE" && payload.eventType !== "form_response") {
    return new Response(JSON.stringify({ skipped: true, eventType: payload.eventType }), {
      headers: { "content-type": "application/json" },
    });
  }

  const fields = payload.data?.fields ?? [];
  const closer = str(findField(fields, /pr[eé]nom.*nom/i)) ?? "Unknown";
  const submitDateRaw = payload.data?.createdAt ?? new Date().toISOString();
  const submitDate = submitDateRaw.slice(0, 10);

  const callsPlanifies = num(findField(fields, /calls? planifi[eé]s/i));
  const callsRecus = num(findField(fields, /calls? re[cç]us/i));
  const followUps = num(findField(fields, /follow.?up/i));
  const acomptes = num(findField(fields, /acomptes?/i));
  const ventesSetting = num(findField(fields, /ventes? .* setting/i));
  const ventesVsl = num(findField(fields, /ventes? .* vsl/i));
  const cashContracte = num(findField(fields, /cash contract/i));
  const cashCollecte = num(findField(fields, /cash collect/i));
  const qualifLead = (() => {
    const v = findField(fields, /qualification.*leads?/i);
    return v == null ? null : Math.round(num(v));
  })();
  const debrief = str(findField(fields, /d[eé]brief|commentaires/i));

  const fathomUrls: string[] = fields
    .filter((f) => /enregistrement.*appel/i.test(f.label || ""))
    .map((f) => str(f.value))
    .filter((v): v is string => !!v && v.includes("fathom.video"));

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const sb = createClient(supabaseUrl, serviceRoleKey, { auth: { persistSession: false } });

  const row = {
    network_id: payload.data.responseId,
    closer_name: closer,
    submit_date: submitDate,
    calls_planifies: callsPlanifies,
    calls_recus: callsRecus,
    follow_ups: followUps,
    acomptes,
    ventes_setting: ventesSetting,
    ventes_vsl: ventesVsl,
    cash_contracte: cashContracte,
    cash_collecte: cashCollecte,
    qualif_lead: qualifLead,
    debrief,
    fathom_urls: fathomUrls.length ? fathomUrls : null,
    raw: payload,
  };

  const { error } = await sb
    .from("fact_eod_closeuse")
    .upsert([row], { onConflict: "network_id" });

  if (error) {
    return new Response(JSON.stringify({ error: error.message, row }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({ ok: true, response_id: payload.data.responseId, closer, submit_date: submitDate }),
    { headers: { "content-type": "application/json" } },
  );
});
