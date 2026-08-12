alter table assl_private.candidate_outcomes
    add column id bigint generated always as identity primary key;

create index screening_runs_watchlist_version_idx
    on assl_private.screening_runs (watchlist_version_id);
create index screening_runs_algorithm_version_idx
    on assl_private.screening_runs (algorithm_version_id);
create index published_snapshots_algorithm_version_idx
    on assl_private.published_snapshots (algorithm_version_id);
