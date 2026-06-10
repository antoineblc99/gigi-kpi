/**
 * Mode opérateur — keys not prompts.
 * L'URL /op/<DECISION_ACT_SECRET> pose un cookie httpOnly "op" dont la valeur
 * est le SHA-256 du secret. La page et la server action vérifient ce hash.
 * Server-side uniquement : le secret ne quitte jamais le serveur.
 */
import { createHash } from "crypto";
import { cookies } from "next/headers";

export const OP_COOKIE = "op";

export function opHash(): string | null {
  const secret = process.env.DECISION_ACT_SECRET;
  if (!secret) return null;
  return createHash("sha256").update(secret).digest("hex");
}

export async function isOperator(): Promise<boolean> {
  const expected = opHash();
  if (!expected) return false;
  const store = await cookies();
  return store.get(OP_COOKIE)?.value === expected;
}
