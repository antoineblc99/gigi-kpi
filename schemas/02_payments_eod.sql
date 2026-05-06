-- gigi-data-os — Payments + EOD Closer schema (Phase 1, Session C)
-- Adds fact_eod_closeuse + extends dim_lead + fact_payment.
-- Applied as Supabase migration `phase_1_session_c_payments_eod`.

create table if not exists fact_eod_closeuse (
  id              bigserial primary key,
  network_id      text unique,                 -- Tally submission id (idempotent upsert)
  closer_id       text references dim_closer(closer_id),
  closer_name     text not null,
  submit_date     date not null,
  calls_planifies int,
  calls_recus     int,
  follow_ups      int,
  acomptes        int,
  ventes_setting  int,
  ventes_vsl      int,
  cash_contracte  numeric,
  cash_collecte   numeric,
  qualif_lead     numeric,
  debrief         text,
  fathom_urls     text[],
  source          text not null default 'tally',
  pulled_at       timestamptz not null default now()
);

create index if not exists fact_eod_closeuse_date_idx
  on fact_eod_closeuse (submit_date desc);
create index if not exists fact_eod_closeuse_closer_idx
  on fact_eod_closeuse (closer_id, submit_date desc);

-- UTM tracking end-to-end
alter table dim_lead add column if not exists fbclid text;

-- Stripe sync
alter table fact_payment add column if not exists stripe_payment_id text;
alter table fact_payment add column if not exists customer_email   text;
alter table fact_payment add column if not exists currency         text default 'eur';
alter table fact_payment add column if not exists refunded_amount  numeric default 0;
alter table fact_payment add column if not exists description      text;
alter table fact_payment add column if not exists metadata         jsonb;
alter table fact_payment add column if not exists source           text default 'stripe';
alter table fact_payment add column if not exists pulled_at        timestamptz default now();

create unique index if not exists fact_payment_stripe_idx
  on fact_payment (stripe_payment_id) where stripe_payment_id is not null;
create index if not exists fact_payment_paid_idx
  on fact_payment (paid_at desc);
create index if not exists fact_payment_email_idx
  on fact_payment (lower(customer_email));
