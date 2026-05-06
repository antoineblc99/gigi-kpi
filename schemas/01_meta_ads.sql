-- gigi-data-os — Meta Ads schema (Phase 1)

create table if not exists dim_campaign (
  id            text primary key,
  name          text not null,
  objective     text,
  status        text,
  daily_budget  numeric,
  account_id    text,
  created_time  timestamptz,
  updated_at    timestamptz not null default now()
);

create table if not exists dim_adset (
  id            text primary key,
  campaign_id   text references dim_campaign(id),
  name          text not null,
  status        text,
  daily_budget  numeric,
  targeting     jsonb,
  created_time  timestamptz,
  updated_at    timestamptz not null default now()
);

create table if not exists dim_creative (
  id              text primary key,
  name            text,
  title           text,
  body            text,
  cta_type        text,
  link_url        text,
  video_id        text,
  image_hash      text,
  thumbnail_url   text,
  hook_text       text,
  object_story_spec jsonb,
  updated_at      timestamptz not null default now()
);

create table if not exists dim_ad (
  id            text primary key,
  adset_id      text references dim_adset(id),
  campaign_id   text references dim_campaign(id),
  creative_id   text references dim_creative(id),
  name          text not null,
  status        text,
  effective_status text,
  video_id      text,
  image_hash    text,
  created_time  timestamptz,
  updated_at    timestamptz not null default now()
);

create table if not exists fact_ad_daily (
  ad_id                  text not null references dim_ad(id),
  date                   date not null,
  spend                  numeric,
  impressions            bigint,
  clicks                 bigint,
  link_clicks            bigint,
  ctr                    numeric,
  cpc                    numeric,
  cpm                    numeric,
  reach                  bigint,
  frequency              numeric,
  landing_page_views     bigint,
  vsl_optin              bigint,
  vsl_call_booked        bigint,
  ig_followers           bigint,
  complete_registration  bigint,
  leads                  bigint,
  video_views            bigint,
  thruplay               bigint,
  post_engagement        bigint,
  actions                jsonb,
  cost_per_action_type   jsonb,
  pulled_at              timestamptz not null default now(),
  primary key (ad_id, date)
);

create index if not exists idx_fact_ad_daily_date on fact_ad_daily(date);
create index if not exists idx_dim_ad_adset on dim_ad(adset_id);
create index if not exists idx_dim_ad_campaign on dim_ad(campaign_id);
create index if not exists idx_dim_adset_campaign on dim_adset(campaign_id);
