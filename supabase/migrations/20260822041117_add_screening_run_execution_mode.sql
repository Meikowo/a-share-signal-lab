alter table assl_private.screening_runs
    add column execution_mode text;

-- Existing records predate explicit provenance. Classify them conservatively as
-- reconstruction so they can never contaminate the forward-only cohort.
update assl_private.screening_runs
set execution_mode = 'historical_reconstruction'
where execution_mode is null;

alter table assl_private.screening_runs
    alter column execution_mode set not null,
    alter column execution_mode set default 'forward_shadow',
    add constraint screening_runs_execution_mode_check
        check (execution_mode in ('historical_reconstruction', 'forward_shadow'));
