import BriefView from "./brief-view";

export const dynamic = "force-dynamic";

async function fetchInitial() {
  const base = process.env.NEXT_PUBLIC_BASE_URL || `http://localhost:${process.env.PORT || 3000}`;
  // Server-side: call generator directly to avoid HTTP self-call during build.
  const { generateBrief } = await import("@/lib/brief");
  const { saveBrief, listBriefs } = await import("@/lib/store");

  // Reuse stored brief if <1h old
  try {
    const recent = await listBriefs(1);
    if (recent.length) {
      const ageMs = Date.now() - new Date(recent[0].created_at).getTime();
      if (ageMs < 60 * 60 * 1000) {
        return {
          markdown: recent[0].markdown,
          generatedAt: recent[0].created_at,
          toolCalls: recent[0].tool_calls ?? 0,
          modelUsed: recent[0].model_used ?? "unknown",
          warnings: [],
          cached: true,
          ageMs,
        };
      }
    }
  } catch {}

  try {
    const result = await generateBrief();
    saveBrief(result).catch(() => {});
    return { ...result, cached: false, ageMs: 0 };
  } catch (e: any) {
    return {
      markdown: `## Erreur de génération\n\n\`${String(e?.message ?? e)}\`\n\nVérifie ANTHROPIC_API_KEY et SUPABASE_DB_URL.`,
      generatedAt: new Date().toISOString(),
      toolCalls: 0,
      modelUsed: "n/a",
      warnings: [String(e?.message ?? e)],
      cached: false,
      ageMs: 0,
    };
  }
}

export default async function Page() {
  const initial = await fetchInitial();
  return <BriefView initial={initial} />;
}
