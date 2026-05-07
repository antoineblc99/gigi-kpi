# Session D — Blockers

## DNS pour `gigi.scale-ia.app` (mineur, non bloquant)
- Le domaine est ajouté au projet Vercel `gigi-communicator` mais le DNS n'est pas configuré.
- **Action Antoine** : sur le registrar de `scale-ia.app`, ajouter :
  ```
  A    gigi    76.76.21.21
  ```
  Ou pointer les nameservers vers `ns1.vercel-dns.com` / `ns2.vercel-dns.com`.
- **En attendant** : alias actif `https://gigi-brief.vercel.app` (fallback prévu).

## Aucun blocker dur
- Anthropic API : OK (claude-opus-4-7, 15 tool calls sur le run live)
- Supabase RPC `execute_readonly_sql` : OK (créé via Management API, grants anon/service_role)
- Brief généré sur des données réelles (151 contacts, 69 surveys, 14 calls)
- Détection automatique des sources manquantes (Meta Ads + Stripe vides → mention claire)

## Notes pour la suite
- La fonction `execute_readonly_sql(query text)` est disponible côté Supabase pour tous les autres agents Phase 2 (Observer, Analyste, Stratège). Pas besoin de réécrire.
- Table `agent_briefs` créée — peut servir de base pour l'historique inter-agents (ajouter colonne `agent` déjà présente).
- Cache : 1h en mémoire process Node + lecture du dernier `agent_briefs`. Pas de KV externe nécessaire pour V1.
