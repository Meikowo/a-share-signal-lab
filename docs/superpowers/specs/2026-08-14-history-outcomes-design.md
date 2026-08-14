# Historical Candidate Outcomes Design

## Goal

Turn the history page from a daily count archive into a usable candidate ledger, while keeping aggregate strategy evaluation on the backtest page.

## Confirmed product scope

- Selecting a date on the history page displays that date's complete `Top10`, `P1`, `P2`, and `风险观察` lists.
- The four lists are tabs. A stock appears only in the bucket stored in that immutable signal snapshot.
- Positive candidates show `T+1`, `T+5`, `T+10`, and `T+20` forward outcomes.
- Each matured horizon shows absolute net return after the existing 10 bp entry and 10 bp exit costs, plus the existing `MAE` value labelled `最大浮亏`.
- An unmatured or unavailable horizon shows `观察中`.
- Risk-watch candidates remain visible in history but are excluded from positive-strategy win-rate statistics.
- The backtest page supports `全部`, `Top10`, `P1`, and `P2` filters and reports sample count, win rate, average net return, and average maximum adverse excursion for each horizon.
- No stock detail drawer or additional database column is added.

## Data design

Published signal payloads remain immutable in Supabase. Forward outcomes are already stored separately in `candidate_outcomes`; public export overlays a privacy-safe subset onto an in-memory copy of each historical payload:

```text
as_of_date + symbol -> [
  { horizon_days, entry_date, exit_date, net_return, mae }
]
```

Only fixed-horizon results with a non-null net return are exported. The stored snapshot hash and stored snapshot JSON are not modified. This preserves signal immutability while allowing the generated static history files to accumulate mature observations.

The public exporter also refreshes `outcome_summary` from the current outcome table instead of waiting for a new signal snapshot. Aggregate outcome rows gain two public fields:

- `bucket`: `all`, `top10`, `p1`, or `p2`
- `avg_mae`: average existing MAE for the selected horizon and bucket

The database query continues to include only successful runs and fixed-horizon positive candidates.

## Interface design

The history page keeps the date selector, count cards, and timeline. Below them it adds a compact tab bar and a read-only outcome table. Desktop rows contain stock/signal plus four horizon cells; mobile rows stack the stock identity above a two-column outcome grid. Each cell presents return first and maximum adverse excursion second.

The backtest page adds the same compact bucket filter above its aggregate table. `净收益` is used instead of benchmark-relative excess return because the user requested absolute performance; copy notes that transaction costs are included.

## Empty, loading, and compatibility behavior

- Dates with no candidates in the selected bucket show a bucket-specific empty state.
- Risk-watch rows show `不纳入正向回测` instead of manufactured forward statistics.
- Old public JSON without `bucket` or `avg_mae` remains readable: the UI treats such rows as `all` and displays missing MAE as `—`.
- Failed history fetches retain the currently shown snapshot and display the existing error notice.

## Privacy and release

The public bundle contains only stocks already present in a public snapshot and five allowlisted outcome fields. It never exports the private universe, fundamental priority, theme tags, holdings, costs, or transactions. Existing privacy scanning runs before the generated bundle replaces the published directory.

Release is complete only after Python tests, web tests, TypeScript/Vite build, Ruff, privacy/export tests, GitHub Actions, and the public site are verified.
