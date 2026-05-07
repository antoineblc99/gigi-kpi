import { sb, runReadOnlySQL } from "./sql";

export async function saveBrief(b: {
  markdown: string;
  toolCalls: number;
  modelUsed: string;
  warnings: string[];
}): Promise<void> {
  const { error } = await sb()
    .from("agent_briefs")
    .insert({
      agent: "communicator",
      markdown: b.markdown,
      tool_calls: b.toolCalls,
      model_used: b.modelUsed,
      warnings: b.warnings,
    });
  if (error) console.error("saveBrief error:", error.message);
}

export type BriefRow = {
  id: number;
  markdown: string;
  tool_calls: number | null;
  model_used: string | null;
  created_at: string;
};

export async function listBriefs(limit = 5): Promise<BriefRow[]> {
  const { rows } = await runReadOnlySQL(
    `select id, markdown, tool_calls, model_used, created_at from agent_briefs where agent = 'communicator' order by created_at desc limit ${Math.min(
      limit,
      20
    )}`
  );
  return rows as BriefRow[];
}
