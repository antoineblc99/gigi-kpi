/**
 * Accès Supabase gigi-data-os via le RPC read-only.
 * Server-side uniquement — la SERVICE_ROLE_KEY ne quitte jamais le serveur.
 * Pattern identique à communicator-app/lib/sql.ts, sans dépendance supabase-js
 * (un POST suffit pour un cockpit read-only).
 */

const URL = process.env.SUPABASE_PROJECT_URL || process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

export async function sql<T = Record<string, unknown>>(query: string): Promise<T[]> {
  if (!URL || !KEY) throw new Error("SUPABASE_PROJECT_URL / SUPABASE_SERVICE_ROLE_KEY manquantes");
  const res = await fetch(`${URL}/rest/v1/rpc/execute_readonly_sql`, {
    method: "POST",
    headers: {
      apikey: KEY,
      Authorization: `Bearer ${KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query: query.trim() }),
    next: { revalidate: 300 }, // ISR : la page se régénère au plus toutes les 5 min
  });
  if (!res.ok) throw new Error(`RPC execute_readonly_sql: HTTP ${res.status}`);
  const data = await res.json();
  if (data?.error) throw new Error(`SQL: ${String(data.error)}`);
  return Array.isArray(data?.rows) ? (data.rows as T[]) : [];
}
