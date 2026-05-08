import { sb, runReadOnlySQL } from "./sql";
import type { BriefData } from "./brief-types";

/** We persist BriefData as JSON.stringify into the existing `markdown` column to
 *  avoid a schema migration. The column is text — JSON survives a roundtrip. */

export async function saveBrief(b: {
  data: BriefData;
  toolCalls: number;
  modelUsed: string;
  warnings: string[];
}): Promise<void> {
  const { error } = await sb()
    .from("agent_briefs")
    .insert({
      agent: "communicator",
      markdown: JSON.stringify(b.data),
      tool_calls: b.toolCalls,
      model_used: b.modelUsed,
      warnings: b.warnings,
    });
  if (error) console.error("saveBrief error:", error.message);
}

export type StoredBrief = {
  id: number;
  data: BriefData | null;
  raw: string;
  tool_calls: number | null;
  model_used: string | null;
  created_at: string;
};

export async function listBriefs(limit = 5): Promise<StoredBrief[]> {
  const { rows } = await runReadOnlySQL(
    `select id, markdown, tool_calls, model_used, created_at from agent_briefs where agent = 'communicator' order by created_at desc limit ${Math.min(
      limit,
      20
    )}`
  );
  return (rows as Array<{ id: number; markdown: string; tool_calls: number | null; model_used: string | null; created_at: string }>).map((r) => ({
    id: r.id,
    raw: r.markdown,
    data: tryParseBriefData(r.markdown),
    tool_calls: r.tool_calls,
    model_used: r.model_used,
    created_at: r.created_at,
  }));
}

function tryParseBriefData(s: string | null): BriefData | null {
  if (!s) return null;
  const trimmed = s.trim();
  if (!trimmed.startsWith("{")) return null; // legacy markdown row
  try {
    const obj = JSON.parse(trimmed);
    if (obj && typeof obj === "object" && obj.meta && obj.tldr && obj.funnels) return obj as BriefData;
    return null;
  } catch {
    return null;
  }
}
