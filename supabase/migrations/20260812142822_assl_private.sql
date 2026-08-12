create schema if not exists assl_private;

revoke all on schema assl_private from public, anon, authenticated, service_role;

create table assl_private.watchlist_versions (
    id uuid primary key,
    created_at timestamptz not null default now(),
    source text not null,
    item_count integer not null check (item_count > 0),
    content_sha256 text not null unique check (content_sha256 ~ '^[0-9a-f]{64}$'),
    note text
);

create table assl_private.watchlist_members (
    watchlist_version_id uuid not null
        references assl_private.watchlist_versions (id) on delete restrict,
    symbol text not null check (symbol ~ '^[0-9]{6}$'),
    name text not null,
    exchange text not null check (exchange in ('SH', 'SZ')),
    fundamental_priority smallint not null default 0
        check (fundamental_priority between 0 and 2),
    theme_tags jsonb,
    primary key (watchlist_version_id, symbol)
);

create table assl_private.daily_bars (
    symbol text not null check (symbol ~ '^[0-9]{6}$'),
    trade_date date not null,
    open numeric not null check (open > 0),
    high numeric not null check (high > 0),
    low numeric not null check (low > 0),
    close numeric not null check (close > 0),
    volume numeric not null check (volume >= 0),
    adjustment text not null check (adjustment = 'qfq'),
    source text not null check (source = 'tencent'),
    source_timestamp timestamptz not null,
    ingested_at timestamptz not null default now(),
    primary key (symbol, trade_date, adjustment, source),
    check (high >= greatest(open, close, low)),
    check (low <= least(open, close, high))
);

create table assl_private.algorithm_versions (
    id text primary key,
    code_sha text not null,
    config jsonb not null,
    created_at timestamptz not null default now(),
    description text not null
);

create table assl_private.screening_runs (
    id uuid primary key,
    as_of_date date not null,
    watchlist_version_id uuid not null
        references assl_private.watchlist_versions (id) on delete restrict,
    algorithm_version_id text not null
        references assl_private.algorithm_versions (id) on delete restrict,
    status text not null check (status in ('running', 'succeeded', 'failed', 'skipped')),
    universe_count integer not null check (universe_count > 0),
    covered_count integer not null default 0
        check (covered_count >= 0 and covered_count <= universe_count),
    coverage_ratio numeric not null default 0
        check (coverage_ratio >= 0 and coverage_ratio <= 1),
    missing_symbols jsonb not null default '[]'::jsonb,
    source_timestamp timestamptz,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    error_stage text,
    error_summary text,
    unique (as_of_date, watchlist_version_id, algorithm_version_id),
    check (jsonb_typeof(missing_symbols) = 'array')
);

create table assl_private.signal_results (
    run_id uuid not null references assl_private.screening_runs (id) on delete restrict,
    symbol text not null check (symbol ~ '^[0-9]{6}$'),
    overall_rank integer check (overall_rank is null or overall_rank > 0),
    public_bucket text check (
        public_bucket is null or public_bucket in ('top10', 'p1', 'p2', 'risk_watch')
    ),
    signal_channel text not null check (
        signal_channel in (
            'confirmed_trend', 'bottom_divergence', 'predictive_cross', 'neutral'
        )
    ),
    grade text not null check (grade in ('强S', 'S', 'A+', 'A', 'B+', 'B', '未评级')),
    signal_date date,
    dif numeric not null,
    dea numeric not null,
    macd_hist numeric not null,
    gap numeric not null,
    gap_convergence numeric,
    x1 numeric,
    x1_change_pct numeric,
    projected_days numeric,
    ma20 numeric,
    ma30 numeric,
    ma60 numeric,
    close_vs_ma20 numeric,
    close_vs_ma30 numeric,
    close_vs_ma60 numeric,
    volume_ratio_5_20 numeric,
    bottom_divergence boolean not null,
    top_divergence boolean not null,
    confirm_price numeric,
    invalidation_price numeric,
    details jsonb not null default '{}'::jsonb,
    primary key (run_id, symbol),
    check (jsonb_typeof(details) = 'object')
);

create table assl_private.published_snapshots (
    run_id uuid primary key references assl_private.screening_runs (id) on delete restrict,
    as_of_date date not null,
    algorithm_version_id text not null
        references assl_private.algorithm_versions (id) on delete restrict,
    payload jsonb not null,
    payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
    published_at timestamptz not null default now(),
    unique (as_of_date, algorithm_version_id),
    check (jsonb_typeof(payload) = 'object')
);

create table assl_private.candidate_outcomes (
    run_id uuid not null references assl_private.screening_runs (id) on delete restrict,
    symbol text not null check (symbol ~ '^[0-9]{6}$'),
    model text not null check (model in ('fixed_horizon', 'signal_exit')),
    horizon_days integer,
    entry_date date,
    entry_price numeric,
    exit_date date,
    exit_price numeric,
    gross_return numeric,
    net_return numeric,
    benchmark_return numeric,
    excess_return numeric,
    mfe numeric,
    mae numeric,
    exit_reason text,
    cost_model_version text not null default 'cost-v1',
    updated_at timestamptz not null default now(),
    unique nulls not distinct (run_id, symbol, model, horizon_days),
    check (
        (model = 'fixed_horizon' and horizon_days in (1, 5, 10, 20))
        or (model = 'signal_exit' and horizon_days is null)
    )
);

create index daily_bars_symbol_date_idx
    on assl_private.daily_bars (symbol, trade_date desc);
create index screening_runs_date_idx
    on assl_private.screening_runs (as_of_date desc);
create index signal_results_rank_idx
    on assl_private.signal_results (run_id, overall_rank);
create index outcomes_lookup_idx
    on assl_private.candidate_outcomes (run_id, symbol, model);

alter table assl_private.watchlist_versions enable row level security;
alter table assl_private.watchlist_members enable row level security;
alter table assl_private.daily_bars enable row level security;
alter table assl_private.algorithm_versions enable row level security;
alter table assl_private.screening_runs enable row level security;
alter table assl_private.signal_results enable row level security;
alter table assl_private.published_snapshots enable row level security;
alter table assl_private.candidate_outcomes enable row level security;

revoke all on all tables in schema assl_private
    from public, anon, authenticated, service_role;
revoke all on all sequences in schema assl_private
    from public, anon, authenticated, service_role;
revoke all on all routines in schema assl_private
    from public, anon, authenticated, service_role;

alter default privileges for role postgres in schema assl_private
    revoke all on tables from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema assl_private
    revoke all on sequences from public, anon, authenticated, service_role;
alter default privileges for role postgres in schema assl_private
    revoke all on routines from public, anon, authenticated, service_role;
