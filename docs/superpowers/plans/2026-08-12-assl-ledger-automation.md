# ASSL Ledger and Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add immutable public snapshots, forward outcome evaluation, privacy-checked static data export, legacy-history import, and a reliable scheduled GitHub Actions pipeline.

**Architecture:** The Plan 1 daily pipeline remains the source of private signals. This plan appends outcome evaluators and a whitelist publisher, persists sanitized immutable payloads in Supabase, and makes GitHub Actions emit a static `public-data` artifact without exposing private database access to browsers.

**Tech Stack:** Python 3.12, psycopg 3, pandas, pytest, JSON Schema, GitHub Actions, Supabase Postgres.

## Global Constraints

- Plan 1 completion gate must pass before this plan starts.
- A published signal snapshot never changes; future outcomes are stored separately.
- Fixed-horizon entry is T+1 open; exits are 1/5/10/20-session closes.
- Signal-exit conditions detected at close execute at the next available session open.
- Cost model `cost-v1` deducts 10 bps on entry and 10 bps on exit.
- Benchmark is CSI 300 over the same entry/exit interval.
- Public data may contain only Top 10, P1/P2, 3–5 risk observations, aggregate outcomes, run metadata, and methodology.
- Fewer than 30 matured samples is labeled `insufficient_sample`; headline win rate is omitted.
- A failed or skipped run never replaces the last successful Pages data bundle.

## File Map

- `src/assl/outcomes.py` — fixed-horizon and signal-exit evaluation.
- `src/assl/publish/schema.py` — explicit public payload dataclasses and serialization.
- `src/assl/publish/exporter.py` — immutable snapshot persistence and bundle generation.
- `src/assl/publish/privacy.py` — content and credential leak scanning.
- `src/assl/legacy.py` — one-time import of validated 2026-08-07 through 2026-08-12 outputs.
- `src/assl/pipeline.py` — outcome update and snapshot stages added to the daily run.
- `schemas/public-snapshot.schema.json` — machine-validated public JSON contract.
- `scripts/run_daily.py` — CI-safe entry point with exit codes.
- `scripts/import_legacy.py` — one-time private importer.
- `.github/workflows/ci.yml` — test workflow.
- `.github/workflows/daily.yml` — scheduled/manual data workflow.
- `tests/` — outcome, schema, privacy, legacy, and workflow contract tests.

---

### Task 1: Implement Fixed-Horizon Outcome Evaluation

**Files:**
- Create: `src/assl/outcomes.py`
- Create: `tests/test_outcomes_fixed.py`

**Interfaces:**
- Consumes: `StockSignal`, ordered `Bar` sequences for candidate and CSI 300
- Produces: frozen `CandidateOutcome` dataclass with run/symbol/model/horizon, entry, trigger detection date, exit, returns, benchmark/excess, MFE/MAE, exit reason, evaluability reason, and cost version
- Produces: `evaluate_fixed_horizon(signal, bars, benchmark_bars, horizon, cost_bps=10) -> CandidateOutcome | None`
- Produces: `matured_horizons(signal_date, bars) -> tuple[int, ...]`

- [ ] **Step 1: Write failing entry/exit and return tests**

```python
def test_fixed_horizon_uses_t_plus_1_open_and_close():
    outcome = evaluate_fixed_horizon(signal_on("2026-08-10"), stock_bars(), benchmark_bars(), horizon=1)
    assert outcome.entry_date == date(2026, 8, 11)
    assert outcome.entry_price == Decimal("10.00")
    assert outcome.exit_date == date(2026, 8, 11)
    assert outcome.exit_price == Decimal("10.50")
    assert outcome.gross_return == Decimal("0.05")
    assert outcome.net_return == Decimal("0.047902")

def test_missing_t_plus_1_open_is_not_fabricated():
    assert evaluate_fixed_horizon(signal_on("2026-08-10"), bars_with_missing_open(), benchmark_bars(), 1) is None
```

The expected net return is `(10.50 * 0.999) / (10.00 * 1.001) - 1`, rounded half-even to six decimals.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_outcomes_fixed.py -v`  
Expected: FAIL because outcome functions are absent.

- [ ] **Step 3: Implement horizon evaluation**

Define this immutable result:

```python
@dataclass(frozen=True, slots=True)
class CandidateOutcome:
    run_id: UUID
    symbol: str
    model: str
    horizon_days: int | None
    entry_date: date | None
    entry_price: Decimal | None
    detection_date: date | None
    exit_date: date | None
    exit_price: Decimal | None
    gross_return: Decimal | None
    net_return: Decimal | None
    benchmark_return: Decimal | None
    excess_return: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    exit_reason: str | None
    non_evaluable_reason: str | None
    cost_model_version: str
```

Use `Decimal` for persisted returns. Horizon 1 exits at T+1 close; horizon 5 exits at the fifth completed trading session after T, and likewise for 10/20. Align benchmark by exact entry and exit dates. MFE is maximum `high / adjusted_entry_cost - 1`; MAE is minimum `low / adjusted_entry_cost - 1` inside the holding interval.

Return `None` plus a repository-recorded non-evaluable reason for suspension, missing open, missing benchmark, or insufficient horizon data. Do not shift to a later entry unless the algorithm version explicitly changes.

- [ ] **Step 4: Test all horizons, costs, MFE/MAE, and benchmark excess**

Run: `python -m pytest tests/test_outcomes_fixed.py -v`  
Expected: all pass.

- [ ] **Step 5: Commit fixed-horizon outcomes**

```bash
git add src/assl/outcomes.py tests/test_outcomes_fixed.py
git commit -m "feat: evaluate fixed-horizon outcomes"
```

---

### Task 2: Implement Signal-Based Exit Evaluation

**Files:**
- Modify: `src/assl/outcomes.py`
- Create: `tests/test_outcomes_signal_exit.py`

**Interfaces:**
- Produces: `detect_signal_exit(indicator_frame, top_divergences) -> ExitTrigger | None`
- Produces: `evaluate_signal_exit(signal, bars, indicators, benchmark_bars, cost_bps=10) -> CandidateOutcome | None`

- [ ] **Step 1: Write close-confirmation/next-open tests**

```python
@pytest.mark.parametrize(("reason", "expected_exit_date", "expected_exit_price"), [
    ("gap_expanded_two_days", date(2026, 8, 14), Decimal("10.42")),
    ("below_ma20_1_5pct", date(2026, 8, 14), Decimal("9.81")),
    ("top_divergence", date(2026, 8, 14), Decimal("11.06")),
])
def test_signal_exit_executes_next_open(reason, expected_exit_date, expected_exit_price):
    outcome = evaluate_signal_exit(signal(), bars_for_trigger(reason), indicators_for_trigger(reason), benchmark_bars())
    assert outcome.exit_reason == reason
    assert outcome.detection_date == date(2026, 8, 13)
    assert outcome.exit_date == expected_exit_date
    assert outcome.exit_price == expected_exit_price
```

Add a test proving a trigger detected on T+3 close cannot exit at T+3 close.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_outcomes_signal_exit.py -v`  
Expected: FAIL because signal-exit functions are absent.

- [ ] **Step 3: Implement stable trigger priority**

`ExitTrigger` is a frozen dataclass containing `reason: str` and `detection_date: date`.

Evaluate triggers after entry in this order when multiple occur on the same close:

1. `below_ma20_1_5pct`;
2. `gap_expanded_two_days`;
3. `top_divergence`.

Record detection date separately from execution date. If the next session has no valid open, leave the outcome pending instead of inventing a fill.

- [ ] **Step 4: Run signal-exit and fixed-horizon tests together**

Run: `python -m pytest tests/test_outcomes_fixed.py tests/test_outcomes_signal_exit.py -v`  
Expected: pass, with the two models producing independent records.

- [ ] **Step 5: Commit signal exits**

```bash
git add src/assl/outcomes.py tests/test_outcomes_signal_exit.py
git commit -m "feat: evaluate signal-based exits"
```

---

### Task 3: Define and Validate the Public JSON Contract

**Files:**
- Create: `src/assl/publish/__init__.py`
- Create: `src/assl/publish/schema.py`
- Create: `schemas/public-snapshot.schema.json`
- Create: `tests/test_public_schema.py`

**Interfaces:**
- Produces: `PublicSnapshot.from_run(run, ranked, aggregates) -> PublicSnapshot`
- Produces: `PublicSnapshot.to_dict() -> dict[str, object]`
- Produces: JSON Schema with `$id = "urn:assl:public-snapshot:v1"`

- [ ] **Step 1: Write an allowlist contract test**

```python
ALLOWED_ROOT = {"schema_version", "as_of_date", "generated_at", "algorithm_version",
                "source", "coverage", "summary", "top10", "p1", "p2",
                "risk_watch", "outcome_summary", "disclaimer"}
FORBIDDEN = {"watchlist_version_id", "fundamental_priority", "theme_tags",
             "database_url", "raw_bars", "all_signals"}

def test_public_snapshot_has_only_allowlisted_root_fields(public_snapshot):
    payload = public_snapshot.to_dict()
    assert set(payload) == ALLOWED_ROOT
    assert not FORBIDDEN.intersection(json.dumps(payload, ensure_ascii=False))
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_public_schema.py -v`  
Expected: FAIL because the publish package is absent.

- [ ] **Step 3: Implement explicit nested public types**

Create frozen dataclasses for `PublicCandidate`, `PublicCoverage`, `PublicSummary`, `PublicOutcomeSummary`, and `PublicSnapshot`. Do not pass database dictionaries into serialization. `PublicCandidate` fields are exactly: `rank`, `symbol`, `name`, `bucket`, `grade`, `signal_type`, `signal_date`, `dif`, `dea`, `macd_hist`, `gap`, `convergence_speed`, `x1`, `x1_change_pct`, `projected_days`, `ma20`, `ma30`, `ma60`, `close_vs_ma20`, `close_vs_ma30`, `close_vs_ma60`, `volume_ratio_5_20`, `bottom_divergence`, `top_divergence`, `reason`, `confirm_price`, `invalidation_price`, `risk`, and `outcomes`. Internal fundamental fields and raw pivot arrays are excluded.

The JSON Schema must set `additionalProperties: false` at every object level and require all displayed fields. Nullable predictive fields use `type: ["number", "null"]`.

- [ ] **Step 4: Validate fixture payloads against the schema**

Use `jsonschema` as a development dependency. Test one valid snapshot and invalid snapshots containing an extra `watchlist` field, missing `as_of_date`, and an invalid grade.

Run: `python -m pytest tests/test_public_schema.py -v`  
Expected: pass.

- [ ] **Step 5: Commit the public contract**

```bash
git add src/assl/publish schemas tests/test_public_schema.py pyproject.toml
git commit -m "feat: define sanitized public snapshot schema"
```

---

### Task 4: Persist Immutable Snapshots and Export Static History

**Files:**
- Create: `src/assl/publish/exporter.py`
- Modify: `src/assl/db.py`
- Modify: `src/assl/pipeline.py`
- Create: `tests/test_exporter.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `persist_snapshot(conn, run_id, snapshot) -> str` returning SHA-256
- Produces: `export_public_bundle(repo, output_dir: Path, algorithm_version: str) -> ExportManifest`
- Public files: `manifest.json`, `latest.json`, `history/index.json`, `history/YYYY-MM-DD.json`, `methodology.json`

- [ ] **Step 1: Write immutability and bundle tests**

```python
def test_published_snapshot_cannot_be_changed(repo, snapshot):
    digest = persist_snapshot(repo, RUN_ID, snapshot)
    assert persist_snapshot(repo, RUN_ID, snapshot) == digest
    with pytest.raises(ImmutableSnapshotError):
        persist_snapshot(repo, RUN_ID, changed(snapshot))

def test_export_bundle_latest_points_to_newest_success(tmp_path, repo):
    manifest = export_public_bundle(repo, tmp_path, "macd-v1")
    assert json.loads((tmp_path / "latest.json").read_text("utf-8"))["as_of_date"] == "2026-08-11"
    assert manifest.history_dates == ("2026-08-10", "2026-08-11")
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_exporter.py -v`  
Expected: FAIL because exporter methods are absent.

- [ ] **Step 3: Implement snapshot persistence and outcome merging**

`ExportManifest` is a frozen dataclass with `algorithm_version: str`, `latest_date: str`, `history_dates: tuple[str, ...]`, `file_sha256: dict[str, str]`, and `generated_at: datetime`.

Insert once under `(as_of_date, algorithm_version_id)`. If the same payload hash exists, return it. If a different hash exists, raise and require a new algorithm version. During export, join outcomes without modifying stored payload; emit outcome fields only for matured records.

Write files atomically through a sibling temporary directory, validate every snapshot against the JSON Schema, then replace the output directory only after all files pass.

- [ ] **Step 4: Add outcome update and publish stages to `DailyPipeline`**

New stable stages are `update_outcomes`, `build_snapshot`, and `publish_snapshot`. Outcome failure prevents a new snapshot because published aggregates must be internally consistent. A failed pipeline leaves the previous successful export untouched.

Run: `python -m pytest tests/test_exporter.py tests/test_pipeline.py -v`  
Expected: pass.

- [ ] **Step 5: Commit exporter integration**

```bash
git add src/assl/publish/exporter.py src/assl/db.py src/assl/pipeline.py tests/test_exporter.py tests/test_pipeline.py
git commit -m "feat: persist and export immutable snapshots"
```

---

### Task 5: Add Privacy and Credential Leak Scanning

**Files:**
- Create: `src/assl/publish/privacy.py`
- Create: `tests/test_privacy.py`

**Interfaces:**
- Produces: `scan_public_tree(root: Path, private_symbols: Collection[str]) -> PrivacyReport`
- Produces: `PrivacyViolation(paths: tuple[Path, ...], reasons: tuple[str, ...])`
- Produces: module CLI `python -m assl.publish.privacy PATH`, exit 0 when safe and 4 on a violation

- [ ] **Step 1: Write tests that deliberately leak private content**

```python
@pytest.mark.parametrize("content,reason", [
    ('{"database_url":"postgresql://user:pass@example/db"}', "database_url"),
    ('{"key":"sb_secret_abcdefghijklmnopqrstuvwxyz"}', "supabase_secret"),
    ('{"fundamental_priority":2}', "private_field"),
])
def test_scanner_blocks_credentials_and_private_fields(tmp_path, content, reason):
    (tmp_path / "leak.json").write_text(content, "utf-8")
    report = scan_public_tree(tmp_path, private_symbols=())
    assert reason in report.reasons
    assert not report.safe
```

Add a test with 50 non-public universe symbols in one file; the scanner must flag `private_universe_cluster`. Public candidate symbols from the snapshot are exempt.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_privacy.py -v`  
Expected: FAIL because scanner is absent.

- [ ] **Step 3: Implement text and structured scanning**

`PrivacyReport` is a frozen dataclass with `safe: bool`, `paths: tuple[Path, ...]`, and `reasons: tuple[str, ...]`.

Scan `.json`, `.js`, `.css`, `.html`, `.map`, and `.txt` files. Detect:

- PostgreSQL/Supabase URLs;
- `sb_secret_`, legacy service-role JWT structure, and authorization headers;
- forbidden field names from Task 3;
- more than 20 non-public private-universe symbols in any one output file;
- files named like `watchlist`, `raw_bars`, `signal_results`, `.env`, or database dumps.

Report only path and reason; never echo the leaked secret value.

- [ ] **Step 4: Integrate scanner after export and run tests**

The exporter raises before artifact creation when `report.safe` is false.

Run: `python -m pytest tests/test_privacy.py tests/test_exporter.py -v`  
Expected: pass.

- [ ] **Step 5: Commit privacy guard**

```bash
git add src/assl/publish/privacy.py src/assl/publish/exporter.py tests/test_privacy.py tests/test_exporter.py
git commit -m "feat: block private data from public artifacts"
```

---

### Task 6: Import Existing Validated History Without Rewriting It

**Files:**
- Create: `src/assl/legacy.py`
- Create: `scripts/import_legacy.py`
- Create: `tests/fixtures/legacy_public_sample.json`
- Create: `tests/test_legacy.py`

**Interfaces:**
- Produces: `parse_legacy_screen(path: Path) -> LegacyRun`
- Produces: `import_legacy_run(repo, legacy_run, watchlist_version, algorithm_version) -> UUID`
- CLI: `python scripts/import_legacy.py --screen PATH --predictive PATH --history PATH --as-of YYYY-MM-DD`

- [ ] **Step 1: Write legacy mapping and duplicate tests**

```python
def test_legacy_chinese_fields_map_to_public_candidate(sample_legacy):
    run = parse_legacy_screen(sample_legacy)
    candidate = run.top10[0]
    assert candidate.symbol == "600000"
    assert candidate.grade in {"强S", "S", "A+", "A", "B+", "B"}

def test_import_same_legacy_date_is_idempotent(repo, legacy_run):
    first = import_legacy_run(repo, legacy_run, VERSION, "legacy-macd-v1")
    second = import_legacy_run(repo, legacy_run, VERSION, "legacy-macd-v1")
    assert first == second
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_legacy.py -v`  
Expected: FAIL because legacy importer is absent.

- [ ] **Step 3: Implement strict legacy import**

Map only known fields from the validated 2026-08-07, 08-10, 08-11, and 08-12 files. Require matching `as_of_date`; reject files with mismatched cutoff, missing summary, duplicate symbols, or unknown public grade. Mark algorithm version `legacy-macd-v1` so imported retrospective data is never mixed with live `macd-v1` forward records.

- [ ] **Step 4: Run a private dry-run and import**

Dry-run prints dates, Top 10 count, P1/P2/risk counts, and hashes only. After confirmation, import within one transaction per date. Do not copy the source files into the public repository.

Run: `python -m pytest tests/test_legacy.py -v`  
Expected: pass.

- [ ] **Step 5: Commit importer**

```bash
git add src/assl/legacy.py scripts/import_legacy.py tests/fixtures/legacy_public_sample.json tests/test_legacy.py
git commit -m "feat: import validated legacy signal history"
```

---

### Task 7: Add CI and the Scheduled Data Workflow

**Files:**
- Create: `scripts/run_daily.py`
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/daily.yml`
- Create: `tests/test_workflows.py`
- Create: `docs/operations.md`

**Interfaces:**
- `scripts/run_daily.py` exit codes: 0 success/skip, 2 data-quality failure, 3 pipeline failure, 4 privacy failure
- Workflow artifact: `assl-public-data` containing the validated `public-data/` tree

- [ ] **Step 1: Write workflow contract tests**

```python
def test_daily_workflow_has_schedule_manual_trigger_and_concurrency():
    workflow = yaml.safe_load(Path(".github/workflows/daily.yml").read_text("utf-8"))
    assert "schedule" in workflow["on"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert "ASSL_DATABASE_URL" in Path(".github/workflows/daily.yml").read_text("utf-8")
```

Also assert workflow permissions are `contents: read` until the Pages plan adds deployment permissions.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_workflows.py -v`  
Expected: FAIL because workflows are absent.

- [ ] **Step 3: Implement CI**

`ci.yml` runs on pull requests and pushes to `main`: Python 3.12 setup, dependency cache, Ruff, unit tests, JSON Schema tests, privacy tests, and migration contract tests. Network and Supabase integration tests remain separate and explicit.

- [ ] **Step 4: Implement daily workflow**

Use:

```yaml
on:
  schedule:
    - cron: "17 22 * * 0-4"
  workflow_dispatch:
    inputs:
      as_of:
        description: "Optional completed A-share date, YYYY-MM-DD"
        required: false
        type: string
concurrency:
  group: assl-daily
  cancel-in-progress: false
permissions:
  contents: read
```

The job sets `TZ=Asia/Shanghai`, reads only `secrets.ASSL_DATABASE_URL`, runs `scripts/run_daily.py`, validates and scans `public-data/`, then uploads `assl-public-data`. Use a non-round minute to reduce scheduler congestion. Do not print environment variables.

- [ ] **Step 5: Document configuration and recovery**

`docs/operations.md` must include:

- how to set `ASSL_DATABASE_URL` as a repository secret;
- how to run `workflow_dispatch` for a completed date;
- how to interpret success, skip, coverage failure, database failure, and privacy failure;
- how to verify the last successful snapshot remains untouched;
- how to rotate credentials without committing them;
- GitHub scheduled runs are approximate, not exact to 06:17.

- [ ] **Step 6: Run tests and commit automation**

Run: `python -m pytest tests/test_workflows.py tests/test_privacy.py tests/test_exporter.py -v`  
Expected: pass.

```bash
git add scripts/run_daily.py .github/workflows tests/test_workflows.py docs/operations.md
git commit -m "ci: automate daily ASSL data runs"
```

---

## Plan 2 Completion Gate

```bash
python -m ruff check src scripts tests
python -m pytest -m "not integration and not network" -v
python scripts/run_daily.py --as-of 2026-08-11 --offline
python -m assl.publish.privacy public-data
git status --short
```

Then manually dispatch the workflow for two historical completed dates. Completion requires two successful immutable runs, outcomes updated only when mature, a valid `assl-public-data` artifact, privacy scan success, no private universe in the artifact, and a clean worktree. Request review before Plan 3.
