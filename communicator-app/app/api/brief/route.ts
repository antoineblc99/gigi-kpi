import { NextRequest } from "next/server";
import { generateBrief } from "@/lib/brief";
import { saveBrief, listBriefs } from "@/lib/store";

export const runtime = "nodejs";
export const maxDuration = 300;
export const dynamic = "force-dynamic";

const CACHE_MS = 60 * 60 * 1000;

let cached: { at: number; payload: any } | null = null;

export async function GET(req: NextRequest) {
  const force = req.nextUrl.searchParams.get("force") === "1";
  const now = Date.now();

  if (!force && cached && now - cached.at < CACHE_MS) {
    return Response.json({ ...cached.payload, cached: true, ageMs: now - cached.at });
  }

  if (!force && !cached) {
    try {
      const recent = await listBriefs(1);
      const r = recent[0];
      if (r?.data) {
        const ageMs = now - new Date(r.created_at).getTime();
        if (ageMs < CACHE_MS) {
          const payload = {
            data: r.data,
            generatedAt: r.created_at,
            toolCalls: r.tool_calls ?? 0,
            modelUsed: r.model_used ?? "unknown",
            warnings: [],
          };
          cached = { at: now - ageMs, payload };
          return Response.json({ ...payload, cached: true, ageMs });
        }
      }
    } catch {
      // ignore
    }
  }

  try {
    const result = await generateBrief();
    saveBrief(result).catch((e) => console.error("saveBrief failed", e));
    cached = { at: now, payload: result };
    return Response.json({ ...result, cached: false, ageMs: 0 });
  } catch (e: any) {
    return Response.json(
      { error: String(e?.message ?? e) },
      { status: 500 }
    );
  }
}
