import { listBriefs } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const briefs = await listBriefs(5);
    return Response.json({ briefs });
  } catch (e: any) {
    return Response.json({ briefs: [], error: String(e?.message ?? e) }, { status: 200 });
  }
}
