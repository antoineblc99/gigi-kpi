import { createClient, SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

export function sb(): SupabaseClient {
  if (client) return client;
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing");
  client = createClient(url, key, { auth: { persistSession: false } });
  return client;
}

export async function runReadOnlySQL(
  query: string
): Promise<{ rows: any[]; rowCount: number; error?: string }> {
  const trimmed = query.trim();
  if (!trimmed) return { rows: [], rowCount: 0, error: "Empty query." };
  const { data, error } = await sb().rpc("execute_readonly_sql", { query: trimmed });
  if (error) return { rows: [], rowCount: 0, error: error.message };
  if (data?.error) return { rows: [], rowCount: 0, error: String(data.error) };
  const rows: any[] = Array.isArray(data?.rows) ? data.rows : [];
  return { rows, rowCount: typeof data?.rowCount === "number" ? data.rowCount : rows.length };
}

export async function listTables(): Promise<string[]> {
  const { rows } = await runReadOnlySQL(
    "select table_name from information_schema.tables where table_schema = 'public' order by table_name"
  );
  return rows.map((r) => r.table_name);
}
