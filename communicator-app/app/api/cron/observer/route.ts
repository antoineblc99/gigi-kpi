import { NextRequest } from "next/server";
import { runObserver } from "@/lib/observer";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

/**
 * Vercel cron endpoint — Observer agent
 *
 * Schedule: see vercel.json crons[] (4× per day at 8h, 13h, 18h, 22h Paris)
 *
 * Auth:
 *  - Vercel cron sends header `Authorization: Bearer ${CRON_SECRET}`
 *  - We verify against env CRON_SECRET to reject manual unauthenticated hits
 */
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization");
  const expected = `Bearer ${process.env.CRON_SECRET}`;
  const isVercelCron = auth === expected;
  const isManual = req.nextUrl.searchParams.get("manual") === "1";
  if (!isVercelCron && !isManual) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  const result = await runObserver();
  return Response.json(result);
}
