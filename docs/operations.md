# ASSL Operations

The daily workflow starts at 06:17 Asia/Shanghai on weekdays and resolves the
latest completed A-share session. A manual run may provide an explicit completed
date. The workflow never changes the private watchlist and never places orders.

Configure one repository secret named `ASSL_DATABASE_URL` with the trusted
Supabase Postgres connection string. Do not expose `assl_private` through the
Supabase Data API. Public artifacts are generated only after the allowlist
serializer and privacy scan pass.

Manual watchlist sync is preview-first:

```text
assl sync-watchlist export.json --source manual
assl sync-watchlist export.json --source manual --apply
```

The first command prints counts and at most 20 changed symbols. Only the second
creates an immutable private version.

A newly applied watchlist version is used by every enabled strategy on the next
screening run. It does not rewrite a signal snapshot that has already been
published for a completed session.

To reconstruct roughly one month from cached qfq bars, manually dispatch the
daily workflow with `backfill_sessions` set to `22`. The command processes the
benchmark trading calendar from oldest to newest and never requests future
bars. The reconstruction uses the current watchlist for every historical date,
so it is useful for calibration but carries selection and survivorship bias; it
must not be presented as a pure forward result.
