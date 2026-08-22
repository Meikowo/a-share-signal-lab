# Strategy Lab and One-Month Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated Strategy Lab page to ASSL and provide a safe command that reconstructs roughly one month of MACD history from cached daily bars.

**Architecture:** Keep the current MACD ranking as the production baseline and present future factors as separate shadow strategies. Backfill runs the current algorithm against the latest private watchlist on each historical trading date, in chronological order, using only bars available through that date; the output is explicitly labeled as a retrospective reconstruction rather than a forward sample.

**Tech Stack:** Python 3.12, pytest, PostgreSQL/Supabase, React 19, TypeScript, Vitest, Vite, GitHub Actions/Pages.

## Global Constraints

- Never publish the complete private watchlist or private research metadata.
- Never use bars dated after the reconstructed signal date.
- Preserve immutable published signal snapshots.
- A watchlist update affects every enabled strategy on the next run; it does not rewrite an already-published date.
- Historical reconstruction uses the latest available watchlist and must disclose selection/survivorship bias.

---

### Task 1: Strategy Lab route

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Test: `web/tests/app.test.tsx`

**Interfaces:**
- Consumes: the existing hash-router and `Snapshot.algorithm_version`
- Produces: `#/lab`, an independent Strategy Lab page with production and shadow-strategy states

- [ ] Write a failing UI test that navigates to `#/lab` and expects the baseline, isolation rule, and four research directions.
- [ ] Run `npm run test:run -- app.test.tsx` and verify the route is absent.
- [ ] Add the route, accessible navigation item, page markup, and responsive styling.
- [ ] Run the focused test and full web test suite.

### Task 2: Trading-session selection and backfill command

**Files:**
- Modify: `src/assl/db.py`
- Modify: `src/assl/cli.py`
- Modify: `tests/fakes.py`
- Test: `tests/test_db.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `AsslRepository.recent_trade_dates(connection, symbol, end_date, limit)`
- Produces: `assl backfill --sessions 22`, running historical dates oldest to newest with `offline=True`

- [ ] Write failing repository and CLI tests for the 22-session selection, chronological execution, and input validation.
- [ ] Run the focused tests and confirm the missing behavior causes the failures.
- [ ] Implement the minimal repository query and CLI orchestration.
- [ ] Run focused and full Python tests.

### Task 3: Operations and manual workflow

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `docs/operations.md`
- Modify: `docs/research-directions.md`
- Test: `tests/test_pages_workflow.py`

**Interfaces:**
- Consumes: GitHub `workflow_dispatch` input `backfill_sessions`
- Produces: an explicit, manually triggered one-month reconstruction without making every daily run expensive

- [ ] Write a failing workflow contract test for the optional backfill input and command.
- [ ] Run the focused test and verify failure.
- [ ] Add the dispatch input and conditional backfill step, then document watchlist and bias semantics.
- [ ] Run the focused and full test suites.

### Task 4: Verification and publication

**Files:**
- No production files beyond fixes required by verification.

**Interfaces:**
- Consumes: the completed implementation
- Produces: verified build and deployed GitHub Pages update

- [ ] Run all Python tests.
- [ ] Run all web tests and the production web build.
- [ ] Inspect the final diff for private data and unrelated changes.
- [ ] Commit the verified changes, push `main`, and confirm the GitHub Pages workflow result.
