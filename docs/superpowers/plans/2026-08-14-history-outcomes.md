# Historical Candidate Outcomes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-stock forward outcomes to historical daily lists and bucket-filtered aggregate performance to the backtest page.

**Architecture:** Keep stored signal snapshots immutable and enrich only generated public JSON with fixed-horizon outcomes queried from the private database. Extend aggregate outcome rows with a public bucket and average MAE, then render the two layers through typed React components with backward-compatible fallbacks.

**Tech Stack:** Python 3.12, psycopg/Postgres, pytest, React 19, TypeScript, Vitest, Testing Library, Vite, GitHub Pages.

## Global Constraints

- Use existing horizons `1`, `5`, `10`, and `20` trading days.
- Use existing `net_return` as absolute performance after 10 bp entry and 10 bp exit costs.
- Use existing `mae` as `最大浮亏`; do not add or migrate a database column.
- Never publish the private watchlist or private research metadata.
- Risk-watch candidates are history-only and excluded from positive-strategy aggregate statistics.
- Unmatured outcomes render as `观察中`.

---

### Task 1: Public outcome export contract

**Files:**
- Modify: `src/assl/db.py`
- Modify: `src/assl/publish/exporter.py`
- Test: `tests/test_db.py`
- Test: `tests/test_exporter.py`

**Interfaces:**
- Produces: `AsslRepository.list_public_candidate_outcomes(algorithm_version, *, connection=None) -> tuple[dict[str, object], ...]`.
- Produces: `attach_candidate_outcomes(payloads, outcomes) -> tuple[dict[str, object], ...]` in the exporter.
- Each exported outcome has exactly `horizon_days`, `entry_date`, `exit_date`, `net_return`, and `mae`.

- [ ] **Step 1: Write failing repository and exporter tests**

Add a repository test whose recording result contains an outcome row and asserts the returned public dictionary and SQL restrictions. Add an exporter test that stores a Top10 signal for `2026-08-12`, returns a T+1 outcome, exports the bundle, and asserts the historical candidate contains that outcome while the repository's stored payload still has an empty `outcomes` array.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
python -m pytest tests/test_db.py tests/test_exporter.py -q
```

Expected: failure because `list_public_candidate_outcomes` and export overlay behavior do not exist.

- [ ] **Step 3: Implement the repository query and pure overlay**

Query successful runs, join `candidate_outcomes` to `signal_results`, select only `fixed_horizon` rows with non-null `net_return` and buckets `top10`, `p1`, or `p2`, and return ISO dates plus numeric values. Deep-copy snapshot payloads before assigning sorted outcomes by `(as_of_date, symbol)`.

- [ ] **Step 4: Run focused tests and verify pass**

Run the command from Step 2. Expected: all focused tests pass and the immutable source payload assertion succeeds.

- [ ] **Step 5: Commit the data-export slice**

```powershell
git add src/assl/db.py src/assl/publish/exporter.py tests/test_db.py tests/test_exporter.py
git commit -m "Add outcomes to exported history"
```

### Task 2: Bucketed aggregate statistics

**Files:**
- Modify: `src/assl/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Extends `AsslRepository.outcome_summary(...)` rows with `bucket` and `avg_mae`.
- `bucket` is one of `all`, `top10`, `p1`, or `p2`.

- [ ] **Step 1: Write the failing summary contract test**

Return recording rows for `all` and `top10`, then assert `bucket`, `avg_mae`, and the existing sample/win/net/excess values are retained. Assert SQL joins `signal_results`, filters positive buckets, and averages `outcome.mae`.

- [ ] **Step 2: Run the focused test and verify failure**

```powershell
python -m pytest tests/test_db.py -q
```

Expected: failure because current summary dictionaries omit `bucket` and `avg_mae`.

- [ ] **Step 3: Implement all-plus-bucket aggregation**

Build one eligible CTE and aggregate it once for `all` and once by `public_bucket` using `union all`. Order results by bucket and horizon, and expose average MAE without changing the schema.

- [ ] **Step 4: Run repository tests and verify pass**

Run the command from Step 2. Expected: all repository tests pass.

- [ ] **Step 5: Commit aggregate statistics**

```powershell
git add src/assl/db.py tests/test_db.py
git commit -m "Group outcome statistics by signal bucket"
```

### Task 3: Type and render historical candidate outcomes

**Files:**
- Modify: `web/src/data.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/tests/app.test.tsx`

**Interfaces:**
- Produces TypeScript `CandidateOutcome` with five public fields.
- `HistoryCandidateList` consumes a bucket's `Candidate[]` and renders horizon cells through `OutcomeCell`.

- [ ] **Step 1: Write a failing history interaction test**

Mock a historical snapshot containing a Top10 candidate with T+1 net return `0.024` and MAE `-0.013`. Navigate to history, select the earlier date, assert the candidate name, `+2.4%`, `最大浮亏 -1.3%`, three `观察中` cells, and the four bucket tabs are visible. Assert the risk tab says `不纳入正向回测`.

- [ ] **Step 2: Run the focused web test and verify failure**

```powershell
npm.cmd run test:run -- tests/app.test.tsx
```

Expected: failure because history currently renders only counts and a timeline.

- [ ] **Step 3: Implement types and history components**

Type candidate outcomes, add bucket state reset on date change, map each positive candidate's outcomes by horizon, format signed percentages, and render `观察中` when absent. Preserve the existing date selector, timeline, count metrics, and fetch error behavior.

- [ ] **Step 4: Add responsive outcome styling**

Add dedicated history list and outcome-cell classes. Use five columns on desktop and a stacked identity plus 2-by-2 outcomes on narrow screens; retain the current neutral visual system and red/green return colors.

- [ ] **Step 5: Run the focused web test and verify pass**

Run the command from Step 2. Expected: history assertions pass.

- [ ] **Step 6: Commit the history interface**

```powershell
git add web/src/data.ts web/src/App.tsx web/src/styles.css web/tests/app.test.tsx
git commit -m "Show candidate outcomes in signal history"
```

### Task 4: Render bucket-filtered aggregate backtests

**Files:**
- Modify: `web/src/data.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/tests/app.test.tsx`

**Interfaces:**
- Extends `OutcomeSummary` with optional `bucket` and `avg_mae` for compatibility with old JSON.
- Backtest filters `all`, `top10`, `p1`, and `p2` without fetching another file.

- [ ] **Step 1: Replace the aggregate rendering test with the new contract**

Provide `all` and `top10` rows, assert the default table displays average net return and MAE, click `Top10`, and assert the sample count and values switch to that bucket.

- [ ] **Step 2: Run the focused web test and verify failure**

```powershell
npm.cmd run test:run -- tests/app.test.tsx
```

Expected: failure because the page has no bucket filter or MAE column.

- [ ] **Step 3: Implement bucket filtering and compatibility fallback**

Treat rows without `bucket` as `all`; render sample count, win rate, average net return, and average maximum adverse excursion for each horizon. Calculate the maturity notice only from the selected bucket.

- [ ] **Step 4: Run all web tests and build**

```powershell
npm.cmd run test:run
npm.cmd run build
```

Expected: all tests pass and Vite emits a production bundle.

- [ ] **Step 5: Commit the aggregate interface**

```powershell
git add web/src/data.ts web/src/App.tsx web/src/styles.css web/tests/app.test.tsx
git commit -m "Add bucketed backtest outcome metrics"
```

### Task 5: Full verification and release

**Files:**
- Modify if required by fixtures: `web/public/data/fixture/latest.json`
- Verify: `.github/workflows/ci.yml`
- Verify: `.github/workflows/daily.yml`

**Interfaces:**
- Produces a privacy-safe static bundle and a deployable Pages site.

- [ ] **Step 1: Run Python lint and non-network tests**

```powershell
python -m ruff check src tests
python -m pytest -m "not integration and not network" -q
```

Expected: zero lint errors and all selected tests pass.

- [ ] **Step 2: Run frontend tests and production build**

```powershell
npm.cmd run test:run
npm.cmd run build
```

Expected: all tests pass and TypeScript/Vite build succeeds.

- [ ] **Step 3: Inspect changed files and public privacy boundary**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors, only intended files, and no generated secret-bearing files.

- [ ] **Step 4: Push the verified commit sequence to `main`**

Update the remote main ref only after checking it still points at the feature branch's parent or safely rebasing on the newest main.

- [ ] **Step 5: Trigger daily export/deploy and verify production**

Run the daily workflow for the latest completed A-share session, wait for CI and Pages deployment, then verify:

- `data/history/2026-08-12.json` contains matured T+1 outcomes where available.
- Later horizons display as pending rather than fabricated values.
- The history date page renders the candidate list and outcome cells.
- The backtest page switches among aggregate buckets.

- [ ] **Step 6: Record release evidence**

Report the final commit, workflow results, public URL, data cutoff, and exact test counts to the user.
