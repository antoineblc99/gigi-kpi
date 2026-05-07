import { NextRequest } from "next/server";
import { runValidator } from "@/lib/validator";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

/**
 * Vercel cron — Validator agent
 * Runs after each pull (or daily). Verifies data integrity, writes data_health,
 * pings Slack on red. Analytics routines should query data_health to refuse
 * running if overall_status === 'red'.
 */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const expected = `Bearer ${process.env.CRON_SECRET}`;
  const isVercelCron = auth === expected;
  const isManual = req.nextUrl.searchParams.get("manual") === "1";
  if (!isVercelCron && !isManual) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const result = await runValidator();
  return Response.json(result);
}
