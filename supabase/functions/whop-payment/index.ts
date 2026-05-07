// Supabase Edge Function — Whop payment webhook
//
// Receives Whop payment events, upserts into fact_payment idempotent on
// payment_id (Whop's pay_xxx). Match dim_lead by email best-effort.
//
// Configure on Whop: Developer Dashboard → Webhooks → URL =
//   https://<project-ref>.supabase.co/functions/v1/whop-payment
//   Subscribe to events: payment.succeeded, payment.refunded, payment.failed
//   Set signing secret → WHOP_WEBHOOK_SECRET below.
//
// Deploy: supabase functions deploy whop-payment --project-ref <ref>

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

interface WhopPaymentEvent {
  action?: string;          // e.g. "payment.succeeded"
  data?: {
    id: string;             // pay_xxx
    user_email?: string;
    subtotal?: number;
    final_amount?: number;
    currency?: string;
    status?: string;
    payment_method?: string;
    payment_processor?: string;
    refunded_amount?: number;
    paid_at?: string | number;
    created_at?: string | number;
    description?: string;
    customer_name?: string;
    promo_code?: string;
    billing_reason?: string;
    receipt_number?: string;
    [k: string]: unknown;
  };
}

function toIso(v: unknown): string | null {
  if (!v) return null;
  if (typeof v === "number") return new Date(v * 1000).toISOString();
  if (typeof v === "string") {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }
  return null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  // Whop signs webhooks with HMAC SHA256 of body using secret.
  // If WHOP_WEBHOOK_SECRET is set, verify; else accept (dev mode).
  const secret = Deno.env.get("WHOP_WEBHOOK_SECRET");
  const rawBody = await req.text();
  if (secret) {
    const sig = req.headers.get("whop-signature") || req.headers.get("x-whop-signature");
    if (!sig) return new Response("Missing signature", { status: 401 });
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const mac = await crypto.subtle.sign("HMAC", key, enc.encode(rawBody));
    const expected = Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    if (sig !== expected && !sig.endsWith(expected)) {
      return new Response("Invalid signature", { status: 401 });
    }
  }

  let event: WhopPaymentEvent;
  try {
    event = JSON.parse(rawBody);
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  const d = event.data;
  if (!d?.id) {
    return new Response(JSON.stringify({ skipped: true, reason: "no payment id" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const sb = createClient(supabaseUrl, serviceRoleKey, { auth: { persistSession: false } });

  const email = (d.user_email || "").toLowerCase().trim() || null;

  // Best-effort match to dim_lead by lowercase email
  let leadId: string | null = null;
  if (email) {
    const { data } = await sb
      .from("dim_lead")
      .select("lead_id")
      .ilike("email", email)
      .limit(1)
      .maybeSingle();
    leadId = data?.lead_id ?? null;
  }

  const amount = (() => {
    const v = d.final_amount ?? d.subtotal ?? 0;
    return typeof v === "number" ? v : parseFloat(String(v)) || 0;
  })();

  const row = {
    payment_id: d.id,
    stripe_payment_id: null,
    lead_id: leadId,
    customer_email: email,
    amount,
    currency: (d.currency || "eur").toLowerCase(),
    status: (d.status || (event.action?.split(".")[1] ?? "")).toLowerCase() || null,
    payment_method: d.payment_method || d.payment_processor || null,
    description: d.description || null,
    paid_at: toIso(d.paid_at) || toIso(d.created_at),
    refunded_amount: d.refunded_amount ?? 0,
    metadata: {
      promo_code: d.promo_code,
      billing_reason: d.billing_reason,
      customer_name: d.customer_name,
      receipt_number: d.receipt_number,
      whop_event_action: event.action,
    },
    source: "whop",
  };

  const { error } = await sb
    .from("fact_payment")
    .upsert([row], { onConflict: "payment_id" });

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({ ok: true, payment_id: d.id, matched_lead: !!leadId, amount, status: row.status }),
    { headers: { "content-type": "application/json" } },
  );
});
