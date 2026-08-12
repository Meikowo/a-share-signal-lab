# ASSL — A-Share Signal Lab

ASSL is a public research dashboard for a private A-share watchlist. It uses
MACD 12/26/9, MA20/30/60, causal divergence detection, and conditional
predictive-cross calculations to rank roughly ten candidates after each
completed trading session.

## Public/private boundary

The browser reads static, privacy-scanned JSON only. The complete watchlist,
internal fundamental priorities, raw bars, database credentials, and all
unselected signal rows stay in a private Supabase schema and are not exposed to
the website or committed to Git.

## Update and evaluation

The scheduled workflow starts at 06:17 Asia/Shanghai on weekdays and resolves
the latest completed A-share session. Candidate outcomes use T+1 open as entry,
fixed 1/5/10/20-session closes, 10 bps per leg, and CSI 300 as benchmark.
Samples below 30 are labeled insufficient rather than promoted as a win rate.

## Local development

The repository contains synthetic public fixtures only. Install the Python
package with its development dependencies, and install the frontend dependencies
under `web/`. The production workflow injects validated public snapshots at
build time.

## Disclaimer

ASSL provides a research candidate pool and priority order. It does not place
orders and does not constitute investment advice or a promise of future return.
