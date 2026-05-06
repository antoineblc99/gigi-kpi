-- gigi-data-os — schema initial (Phase 1 bootstrap)
-- Convention : lead_id = sha256(lower(email) || e164(phone))
-- Toutes les tables : RLS ON, accès via service_role uniquement.

-- =========================================================================
-- DIMENSIONS
-- =========================================================================

create table if not exists dim_lead (
  lead_id            text primary key,
  email              text,
  phone              text,
  first_name         text,
  last_name          text,
  first_seen         timestamptz not null default now(),
  ad_id_first_touch  text,
  utm_source         text,
  utm_medium         text,
  utm_campaign       text,
  utm_content        text,
  utm_term           text
);
create index if not exists idx_dim_lead_email on dim_lead(email);
create index if not exists idx_dim_lead_phone on dim_lead(phone);

create table if not exists dim_campaign (
  campaign_id text primary key,
  name        text,
  objective   text,
  status      text
);

create table if not exists dim_adset (
  adset_id    text primary key,
  campaign_id text references dim_campaign(campaign_id),
  name        text,
  status      text
);
create index if not exists idx_dim_adset_campaign on dim_adset(campaign_id);

create table if not exists dim_ad (
  ad_id          text primary key,
  name           text,
  campaign_id    text references dim_campaign(campaign_id),
  adset_id       text references dim_adset(adset_id),
  hook_text      text,
  format         text,
  duration_sec   integer,
  thumbnail_url  text,
  created_at     timestamptz default now()
);
create index if not exists idx_dim_ad_campaign on dim_ad(campaign_id);
create index if not exists idx_dim_ad_adset on dim_ad(adset_id);

create table if not exists dim_creative (
  creative_id     text primary key,
  video_id        text,
  hook_transcript text,
  body_text       text,
  cta             text
);

create table if not exists dim_closer (
  closer_id    text primary key,
  name         text,
  email        text,
  calendar_ids text[]
);

-- =========================================================================
-- FAITS
-- =========================================================================

create table if not exists fact_ad_daily (
  ad_id            text not null references dim_ad(ad_id),
  date             date not null,
  spend            numeric(12,2),
  impressions      bigint,
  clicks           bigint,
  lpv              bigint,
  results          bigint,
  cost_per_result  numeric(12,4),
  ctr              numeric(8,4),
  cpc              numeric(12,4),
  cpm              numeric(12,4),
  reach            bigint,
  followers_ig     bigint,
  vsl_optin        bigint,
  vsl_call_booked  bigint,
  primary key (ad_id, date)
);
create index if not exists idx_fact_ad_daily_date on fact_ad_daily(date);

create table if not exists fact_survey (
  survey_id          text primary key,
  lead_id            text references dim_lead(lead_id),
  submitted_at       timestamptz,
  statut_onglerie    text,
  quand_demarrer     text,
  budget             text,
  motivation         text,
  temps_dispo        text,
  qualif_score       numeric(5,2)
);
create index if not exists idx_fact_survey_lead on fact_survey(lead_id);
create index if not exists idx_fact_survey_submitted on fact_survey(submitted_at);

create table if not exists fact_contact (
  contact_id       text primary key,        -- GHL contact_id
  lead_id          text references dim_lead(lead_id),
  source           text,
  tags             text[],
  created_at       timestamptz,
  last_activity_at timestamptz
);
create index if not exists idx_fact_contact_lead on fact_contact(lead_id);

create table if not exists fact_call (
  call_id              text primary key,
  lead_id              text references dim_lead(lead_id),
  calendar_id          text,
  scheduled_at         timestamptz,
  status               text,
  closer_id            text references dim_closer(closer_id),
  fathom_url           text,
  eod_logged_at        timestamptz,
  closer_qualif_score  numeric(5,2)
);
create index if not exists idx_fact_call_lead on fact_call(lead_id);
create index if not exists idx_fact_call_scheduled on fact_call(scheduled_at);
create index if not exists idx_fact_call_closer on fact_call(closer_id);

create table if not exists fact_sale (
  sale_id           text primary key,        -- GHL opportunity_id
  lead_id           text references dim_lead(lead_id),
  contracted_amount numeric(12,2),
  contracted_at     timestamptz,
  source            text,
  closer_id         text references dim_closer(closer_id),
  fathom_url        text
);
create index if not exists idx_fact_sale_lead on fact_sale(lead_id);
create index if not exists idx_fact_sale_contracted_at on fact_sale(contracted_at);

create table if not exists fact_payment (
  payment_id     text primary key,           -- Stripe payment_id
  lead_id        text references dim_lead(lead_id),
  sale_id        text references fact_sale(sale_id),
  amount         numeric(12,2),
  paid_at        timestamptz,
  status         text,
  payment_method text
);
create index if not exists idx_fact_payment_sale on fact_payment(sale_id);
create index if not exists idx_fact_payment_paid on fact_payment(paid_at);

create table if not exists fact_setter_dm (
  dm_id          text primary key,
  lead_id        text references dim_lead(lead_id),
  ig_username    text,
  sent_at        timestamptz,
  replied_at     timestamptz,
  link_sent      boolean,
  response_class text
);
create index if not exists idx_fact_setter_dm_lead on fact_setter_dm(lead_id);
create index if not exists idx_fact_setter_dm_sent on fact_setter_dm(sent_at);

create table if not exists fact_vsl_view (
  view_id        text primary key,
  lead_id        text references dim_lead(lead_id),
  viewed_at      timestamptz,
  watch_seconds  integer,
  completed_pct  numeric(5,2),
  drop_at_sec    integer
);
create index if not exists idx_fact_vsl_view_lead on fact_vsl_view(lead_id);
create index if not exists idx_fact_vsl_view_viewed on fact_vsl_view(viewed_at);

-- =========================================================================
-- AGENT INFRASTRUCTURE
-- =========================================================================

create table if not exists agent_memory (
  id          bigserial primary key,
  agent_name  text not null,
  key         text not null,
  value       jsonb not null,
  updated_at  timestamptz not null default now(),
  unique (agent_name, key)
);
create index if not exists idx_agent_memory_agent on agent_memory(agent_name);

create table if not exists decision_log (
  id            bigserial primary key,
  agent_name    text not null,
  decision_type text not null,
  payload       jsonb not null,
  executed_by   text,
  status        text not null default 'proposed',  -- proposed | approved | executed | rejected | rolled_back
  created_at    timestamptz not null default now(),
  outcome       jsonb
);
create index if not exists idx_decision_log_agent on decision_log(agent_name);
create index if not exists idx_decision_log_status on decision_log(status);
create index if not exists idx_decision_log_created on decision_log(created_at);

-- Cross-client signals : ratios/deltas anonymisés uniquement.
create table if not exists pattern_signals (
  signal_id      bigserial primary key,
  client_slug    text not null,            -- "gigi", "alex", "valentin"... slug seulement
  metric         text not null,
  baseline_value numeric,
  current_value  numeric,
  delta_pct      numeric,
  anonymized     jsonb not null default '{}'::jsonb,
  captured_at    timestamptz not null default now()
);
create index if not exists idx_pattern_signals_metric on pattern_signals(metric);
create index if not exists idx_pattern_signals_client on pattern_signals(client_slug);
create index if not exists idx_pattern_signals_captured on pattern_signals(captured_at);

-- =========================================================================
-- RLS — toutes les tables fermées (service_role uniquement)
-- =========================================================================

alter table dim_lead         enable row level security;
alter table dim_campaign     enable row level security;
alter table dim_adset        enable row level security;
alter table dim_ad           enable row level security;
alter table dim_creative     enable row level security;
alter table dim_closer       enable row level security;
alter table fact_ad_daily    enable row level security;
alter table fact_survey      enable row level security;
alter table fact_contact     enable row level security;
alter table fact_call        enable row level security;
alter table fact_sale        enable row level security;
alter table fact_payment     enable row level security;
alter table fact_setter_dm   enable row level security;
alter table fact_vsl_view    enable row level security;
alter table agent_memory     enable row level security;
alter table decision_log     enable row level security;
alter table pattern_signals  enable row level security;

-- Aucune policy anon : tout reste service_role.
