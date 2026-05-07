// Supabase Edge Function — EOD closeuses webhook (Typeform)
//
// Receives a Typeform form_response webhook, normalizes answers by matching
// answer.field.id ↔ definition.fields[].id, upserts into fact_eod_closeuse.
// Idempotent on Typeform's form_response.token.
//
// Typeform setup:
//   Form → Connect → Webhooks → Add webhook
//   URL: https://<project-ref>.supabase.co/functions/v1/tally-eod
//   Optional secret header: TALLY_WEBHOOK_SECRET (Typeform calls it "secret")
//
// Function name kept as `tally-eod` for backward URL compatibility — payload
// detection works for both Typeform and Tally formats.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

interface TypeformAnswer {
  type: string;             // "text", "number", "choice", "choices", "boolean", "url", ...
  field: { id: string; type: string; ref: string };
  text?: string;
  number?: number;
  boolean?: boolean;
  email?: string;
  url?: string;
  choice?: { label: string };
  choices?: { labels: string[] };
  date?: string;
}

interface TypeformField {
  id: string;
  ref?: string;
  type: string;
  title: string;
  properties?: Record<string, unknown>;
}

interface TypeformPayload {
  event_id?: string;
  event_type?: string;
  form_response?: {
    form_id: string;
    token: string;
    submitted_at: string;
    landed_at?: string;
    definition: { id: string; title: string; fields: TypeformField[] };
    answers: TypeformAnswer[];
  };
  // Tally fallback
  eventType?: string;
  data?: { responseId: string; fields: any[]; createdAt: string };
}

function answerValue(a: TypeformAnswer): string | number | boolean | null {
  if (a.text != null) return a.text;
  if (a.number != null) return a.number;
  if (a.boolean != null) return a.boolean;
  if (a.email) return a.email;
  if (a.url) return a.url;
  if (a.choice?.label) return a.choice.label;
  if (a.choices?.labels?.length) return a.choices.labels.join(", ");
  if (a.date) return a.date;
  return null;
}

function num(v: any): number {
  if (v == null || v === "") return 0;
  if (typeof v === "number") return v;
  const n = parseFloat(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

function strv(v: any): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s || null;
}

/** Build a map { field_title_normalized: answer_value } */
function buildAnswerMap(payload: TypeformPayload): Record<string, any> {
  const fr = payload.form_response;
  if (!fr) return {};
  const fieldsById = new Map(fr.definition.fields.map((f) => [f.id, f]));
  const out: Record<string, any> = {};
  for (const ans of fr.answers ?? []) {
    const f = fieldsById.get(ans.field.id);
    const title = (f?.title ?? "").toLowerCase().trim();
    if (!title) continue;
    out[title] = answerValue(ans);
  }
  return out;
}

function findByLabel(map: Record<string, any>, regex: RegExp): any {
  for (const [k, v] of Object.entries(map)) {
    if (regex.test(k)) return v;
  }
  return null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  // Optional secret check (Typeform sends as "Typeform-Signature" — different scheme,
  // skip strict verification for now; if TALLY_WEBHOOK_SECRET is set we accept any signature presence).
  const webhookSecret = Deno.env.get("TALLY_WEBHOOK_SECRET");
  if (webhookSecret) {
    const got =
      req.headers.get("typeform-signature") ||
      req.headers.get("x-webhook-secret") ||
      req.headers.get("tally-signature");
    if (!got) return new Response("Unauthorized", { status: 401 });
  }

  let payload: TypeformPayload;
  try {
    payload = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  // Detect format: Typeform (form_response) vs Tally (data.fields)
  const isTypeform = !!payload.form_response;
  const isTally = !isTypeform && Array.isArray(payload.data?.fields);

  if (!isTypeform && !isTally) {
    return new Response(
      JSON.stringify({ skipped: true, reason: "unrecognized payload" }),
      { headers: { "content-type": "application/json" } },
    );
  }

  let networkId = "";
  let submitDate = "";
  let answers: Record<string, any> = {};

  if (isTypeform) {
    const fr = payload.form_response!;
    networkId = fr.token;
    submitDate = (fr.submitted_at || new Date().toISOString()).slice(0, 10);
    answers = buildAnswerMap(payload);
  } else {
    const d = payload.data!;
    networkId = d.responseId;
    submitDate = (d.createdAt || new Date().toISOString()).slice(0, 10);
    for (const f of d.fields ?? []) {
      const title = String((f as any).label ?? "").toLowerCase().trim();
      if (title) answers[title] = (f as any).value;
    }
  }

  // Robust label-based extraction (FR Typeform headings of Léa's form)
  const closer = strv(findByLabel(answers, /pr[eé]nom.*nom/i)) ?? "Unknown";
  const callsPlanifies = num(findByLabel(answers, /calls? planifi[eé]s/i));
  const callsRecus = num(findByLabel(answers, /calls? re[cç]us/i));
  const followUps = num(findByLabel(answers, /follow.?up/i));
  const acomptes = num(findByLabel(answers, /acomptes?/i));
  const ventesSetting = num(findByLabel(answers, /ventes?.* setting/i));
  const ventesVsl = num(findByLabel(answers, /ventes?.* vsl/i));
  const cashContracte = num(findByLabel(answers, /cash contract/i));
  const cashCollecte = num(findByLabel(answers, /cash collect/i));
  const qualifLeadRaw = findByLabel(answers, /qualification.*leads?/i);
  const qualifLead = qualifLeadRaw == null ? null : Math.round(num(qualifLeadRaw));
  const debrief = strv(findByLabel(answers, /d[eé]brief|commentaires/i));

  const fathomUrls = Object.entries(answers)
    .filter(([k]) => /enregistrement.*appel/i.test(k))
    .map(([_, v]) => strv(v))
    .filter((v): v is string => !!v && v.includes("fathom.video"));

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const sb = createClient(supabaseUrl, serviceRoleKey, { auth: { persistSession: false } });

  const row = {
    network_id: networkId,
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
    source: isTypeform ? "typeform" : "tally",
  };

  const { error } = await sb
    .from("fact_eod_closeuse")
    .upsert([row], { onConflict: "network_id" });

  if (error) {
    return new Response(
      JSON.stringify({ error: error.message, row }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
  }

  return new Response(
    JSON.stringify({
      ok: true,
      source: row.source,
      network_id: networkId,
      closer,
      submit_date: submitDate,
      cash_contracte: cashContracte,
      ventes: ventesSetting + ventesVsl,
    }),
    { headers: { "content-type": "application/json" } },
  );
});
