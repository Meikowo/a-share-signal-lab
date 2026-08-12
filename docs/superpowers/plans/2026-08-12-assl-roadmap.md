# ASSL Implementation Roadmap

The approved design is implemented through three sequential, independently reviewable plans:

1. [`2026-08-12-assl-core-pipeline.md`](./2026-08-12-assl-core-pipeline.md) — repository foundation, private Supabase schema, watchlist versioning, Tencent OHLCV ingestion, MACD/divergence/predictive-cross engine, deterministic ranking, and a local daily-run CLI.
2. [`2026-08-12-assl-ledger-automation.md`](./2026-08-12-assl-ledger-automation.md) — immutable snapshots, fixed-horizon and signal-exit outcomes, sanitized public-data export, privacy scanning, legacy snapshot import, and scheduled GitHub Actions.
3. [`2026-08-12-assl-public-site.md`](./2026-08-12-assl-public-site.md) — the approved neutral ChatGPT-inspired ASSL interface, history and backtest pages, responsive/accessibility tests, and GitHub Pages deployment.

Each plan ends with a working deliverable:

- Plan 1: `assl run-daily` can produce a deterministic local screening result from a private watchlist and cached bars.
- Plan 2: a scheduled workflow can persist runs/outcomes and emit a privacy-checked static JSON bundle.
- Plan 3: the public Pages site can render that bundle without any private Supabase access.

Execute the plans in this order. Do not start a later plan until the previous plan's verification commands pass and its review gate is complete.

## Design Coverage Check

| Approved design area | Implemented by |
|---|---|
| Public/private architecture and Supabase schema | Plan 1, Tasks 1–4 |
| Watchlist manual sync and version history | Plan 1, Task 4 |
| Tencent qfq OHLCV and data quality | Plan 1, Task 5 |
| MACD, MAs, causal divergence, predicted cross, grades and ranking | Plan 1, Tasks 6–9 |
| Idempotency, coverage threshold, failures and date cutoff | Plan 1, Task 9; Plan 2, Task 7 |
| Immutable snapshots and both outcome models | Plan 2, Tasks 1–4 |
| Public field allowlist and privacy scan | Plan 2, Tasks 3–5 |
| Existing August 2026 history import | Plan 2, Task 6 |
| Weekday 06:17 automation and manual rerun | Plan 2, Task 7 |
| Approved visual design, Today, history, backtest and method pages | Plan 3, Tasks 1–5 |
| Responsive, accessibility and browser privacy tests | Plan 3, Task 6 |
| Public GitHub repository and Pages deployment | Plan 1, Task 1; Plan 3, Task 7 |
| Data/source/version labels and disclaimer | Plan 2 public schema; Plan 3 pages |

No approved design section is intentionally deferred beyond these three plans.
