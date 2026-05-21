-- 03_enable_rls.sql — Active la Row Level Security sur les tables créées
-- après le schéma initial (pipelines / agents) qui l'avaient zappée.
--
-- Contexte : ces tables sont dans le schéma `public`, donc exposées via
-- l'API PostgREST. Sans RLS, la clé `anon` (publique) peut tout lire/écrire.
-- Le Security Advisor Supabase les flagge en erreur.
--
-- Fix : activer RLS SANS policy. Les pipelines/agents utilisent la clé
-- `service_role` qui bypass la RLS → aucun impact. Les clés anon/authenticated
-- se retrouvent bloquées → comportement voulu (tables 100% internes).
--
-- Appliqué le 2026-05-21.

ALTER TABLE public.agent_briefs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_health            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dim_lead               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_calendar_capacity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_call              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_contact           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_eod_closeuse      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_ig_followers      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_sale              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fact_survey            ENABLE ROW LEVEL SECURITY;

-- Verrouille execute_readonly_sql : fonction SECURITY DEFINER qui exécute du
-- SQL arbitraire en bypassant la RLS. Elle était appelable par anon/authenticated
-- → n'importe qui avec la clé publique pouvait dumper auth.users, etc.
-- Seul communicator-app l'appelle, côté serveur, avec la clé service_role.
REVOKE EXECUTE ON FUNCTION public.execute_readonly_sql(text) FROM anon, authenticated, public;
