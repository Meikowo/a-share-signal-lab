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
