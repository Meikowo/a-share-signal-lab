alter table assl_private.screening_runs
    add column result_sha256 text
    check (result_sha256 is null or result_sha256 ~ '^[0-9a-f]{64}$');
