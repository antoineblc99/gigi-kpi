import { NextRequest } from "next/server";
import { runSignals } from "@/lib/signals";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

/**
 * Vercel cron — Signals agent (5h30 UTC, après le validator de 5h).
 * Calcule les signaux business (show rate, leads chauds, capacity, CPL, ads…)
 * et poste dans Slack UNIQUEMENT s'il y a au moins un signal.
 */
export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret) return Response.json({ error: "CRON_SECRET not configured" }, { status: 500 });
  const auth = req.headers.get("authorization");
  const keyParam = req.nextUrl.searchParams.get("key");
  const authorized = auth === `Bearer ${secret}` || keyParam === secret;
  if (!authorized) return Response.json({ error: "unauthorized" }, { status: 401 });
  const result = await runSignals();
  return Response.json(result);
}
