from pathlib import Path

MIGRATIONS = Path("supabase/migrations")


def migration_sql() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS.glob("*.sql"))
    ).lower()


def test_private_schema_and_unique_run_contract_exist():
    sql = migration_sql()

    assert "create schema if not exists assl_private" in sql
    assert "create table assl_private.watchlist_versions" in sql
    assert "create table assl_private.signal_results" in sql
    assert "unique (as_of_date, watchlist_version_id, algorithm_version_id)" in sql


def test_private_schema_is_not_granted_to_data_api_roles():
    sql = migration_sql()

    assert "grant usage on schema assl_private to anon" not in sql
    assert "grant usage on schema assl_private to authenticated" not in sql
    assert "revoke all on schema assl_private from public, anon, authenticated, service_role" in sql


def test_every_private_table_has_rls_enabled():
    sql = migration_sql()
    tables = (
        "watchlist_versions",
        "watchlist_members",
        "daily_bars",
        "algorithm_versions",
        "screening_runs",
        "signal_results",
        "published_snapshots",
        "candidate_outcomes",
    )

    for table in tables:
        assert f"alter table assl_private.{table} enable row level security" in sql


def test_core_lookup_indexes_exist():
    sql = migration_sql()

    assert "daily_bars_symbol_date_idx" in sql
    assert "screening_runs_date_idx" in sql
    assert "signal_results_rank_idx" in sql
    assert "outcomes_lookup_idx" in sql
    assert "screening_runs_watchlist_version_idx" in sql
    assert "screening_runs_algorithm_version_idx" in sql
    assert "published_snapshots_algorithm_version_idx" in sql


def test_candidate_outcomes_has_surrogate_primary_key():
    sql = migration_sql()

    assert "add column id bigint generated always as identity primary key" in sql


def test_screening_run_stores_deterministic_result_hash():
    sql = migration_sql()

    assert "add column result_sha256 text" in sql
