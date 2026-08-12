# ASSL Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic private watchlist-to-ranked-signals pipeline with Supabase persistence and a local `assl run-daily` command.

**Architecture:** A Python package separates domain types, persistence, market-data ingestion, technical indicators, signal classification, ranking, and orchestration. Supabase is accessed only through a Postgres connection from trusted environments; public-site generation is deferred to Plan 2.

**Tech Stack:** Python 3.12, pandas, NumPy, httpx, psycopg 3, pytest, respx, Ruff, PostgreSQL/Supabase.

## Global Constraints

- MACD parameters are exactly 12/26/9; moving averages are exactly 20/30/60.
- Tencent daily OHLCV must use `qfq` and an explicit completed-market-date cutoff.
- The initial universe is every valid A-share in the latest private export; the current reference snapshot contains 839 A-shares.
- No order placement, broker integration, intraday signal, or public watchlist endpoint.
- `assl_private` must not be exposed through the Supabase Data API.
- A screening run is uniquely identified by `(as_of_date, watchlist_version_id, algorithm_version_id)`.
- All ranking weights, rounding, and tie-breaks are stored in the algorithm-version config.
- Existing files under `C:/Users/WINDOWS/.codex/.chatgpt-projects/g-p-6a757eb998988191a724d322dbab4d6c` are read-only references; do not modify them.
- Never print a full watchlist or a database credential to logs.

## File Map

- `pyproject.toml` â€” Python package metadata, dependencies, CLI entry point, pytest and Ruff config.
- `.gitignore` â€” secrets, private snapshots, caches, generated artifacts, and visual-companion files.
- `src/assl/config.py` â€” environment and versioned algorithm configuration.
- `src/assl/domain.py` â€” immutable domain dataclasses and enums shared across modules.
- `src/assl/db.py` â€” Postgres repository and transaction boundaries.
- `src/assl/watchlist.py` â€” export normalization, A-share filtering, hashing, and diffing.
- `src/assl/market/tencent.py` â€” Tencent request construction, parsing, retry, and batching.
- `src/assl/market/quality.py` â€” OHLCV validation and coverage decisions.
- `src/assl/signals/indicators.py` â€” EMA, MACD, MAs, volume ratio, and crossing helpers.
- `src/assl/signals/divergence.py` â€” causal pivot and divergence detection.
- `src/assl/signals/predictive.py` â€” X1 inversion, convergence, P1/P2, and invalidation.
- `src/assl/signals/classify.py` â€” A/B/C channels, top-divergence risk, grade selection.
- `src/assl/ranking.py` â€” deterministic ranking and public-bucket selection.
- `src/assl/pipeline.py` â€” idempotent daily orchestration.
- `src/assl/cli.py` â€” `sync-watchlist` and `run-daily` commands.
- `supabase/migrations/202608120001_assl_private.sql` â€” private schema and core tables.
- `tests/` â€” unit, regression, integration, and fixture data.

---

### Task 1: Bootstrap the Python Package and Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/assl/__init__.py`
- Create: `src/assl/config.py`
- Create: `src/assl/cli.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.from_env() -> Settings`
- Produces: `AlgorithmConfig.macd_v1() -> AlgorithmConfig`
- Produces: console script `assl`

- [ ] **Step 1: Write failing configuration tests**

```python
# tests/test_config.py
import pytest
from assl.config import AlgorithmConfig, Settings

def test_macd_v1_has_frozen_parameters():
    cfg = AlgorithmConfig.macd_v1()
    assert cfg.version == "macd-v1"
    assert (cfg.fast, cfg.slow, cfg.signal) == (12, 26, 9)
    assert cfg.ma_windows == (20, 30, 60)
    assert cfg.publish_coverage == 0.98
    assert cfg.rounding_digits == 6

def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("ASSL_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="ASSL_DATABASE_URL"):
        Settings.from_env()
```

- [ ] **Step 2: Run the tests and verify they fail before package creation**

Run: `python -m pytest tests/test_config.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'assl'`.

- [ ] **Step 3: Add package metadata and minimal configuration implementation**

Use these dependency groups in `pyproject.toml`:

```toml
[project]
name = "a-share-signal-lab"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.27,<1",
  "numpy>=2,<3",
  "pandas>=2.2,<3",
  "psycopg[binary]>=3.2,<4",
]

[project.optional-dependencies]
dev = ["pytest>=8,<9", "pytest-cov>=5,<7", "respx>=0.21,<1", "ruff>=0.8,<1"]

[project.scripts]
assl = "assl.cli:main"
```

Implement frozen dataclasses in `src/assl/config.py`:

```python
@dataclass(frozen=True)
class AlgorithmConfig:
    version: str
    fast: int
    slow: int
    signal: int
    ma_windows: tuple[int, int, int]
    publish_coverage: float
    rounding_digits: int

    @classmethod
    def macd_v1(cls) -> "AlgorithmConfig":
        return cls("macd-v1", 12, 26, 9, (20, 30, 60), 0.98, 6)

@dataclass(frozen=True)
class Settings:
    database_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        value = os.environ.get("ASSL_DATABASE_URL", "").strip()
        if not value:
            raise ValueError("ASSL_DATABASE_URL is required")
        return cls(database_url=value)
```

Make `cli.main()` parse subcommands but print help when none is supplied.

- [ ] **Step 4: Add secret-safe ignore rules and run checks**

`.gitignore` must include:

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
private-data/
public-data/
web/public/data/*
!web/public/data/fixture/
!web/public/data/fixture/**
.superpowers/
node_modules/
dist/
```

Run: `python -m pytest tests/test_config.py -v`  
Expected: 2 passed.  
Run: `python -m ruff check src tests`  
Expected: no violations.

- [ ] **Step 5: Commit the package foundation**

```bash
git add pyproject.toml .gitignore src/assl tests/test_config.py
git commit -m "chore: bootstrap ASSL Python package"
```

- [ ] **Step 6: Create the approved public GitHub repository**

Before publishing, run `git grep -n -E "postgresql://|sb_secret_|service_role|ASSL_DATABASE_URL="` and confirm it finds no credential value. Then create and push the user-approved repository:

```bash
gh repo create a-share-signal-lab --public --source . --remote origin --push
```

Expected: the remote repository is public, `main` is pushed, and it contains only the design/plans plus the secret-safe package foundation. Do not configure any secret until the private schema and workflow are ready.

---

### Task 2: Define Domain Types and Deterministic Serialization

**Files:**
- Create: `src/assl/domain.py`
- Create: `tests/test_domain.py`

**Interfaces:**
- Produces: `Instrument`, `Bar`, `Divergence`, `Prediction`, `StockSignal`, `RankedScreen`
- Produces: `canonical_json(value: object) -> str`
- Produces: `content_sha256(value: object) -> str`

- [ ] **Step 1: Write failing tests for canonical hashes and validation**

```python
from datetime import date
import pytest
from assl.domain import Bar, Instrument, canonical_json, content_sha256

def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert content_sha256({"b": 2, "a": 1}) == content_sha256({"a": 1, "b": 2})

def test_bar_rejects_invalid_ohlc():
    with pytest.raises(ValueError, match="high"):
        Bar("600000", date(2026, 8, 11), 10, 9, 8, 9, 100)

def test_instrument_normalizes_exchange():
    item = Instrument.from_secid("1.600000", "æµ¦å‘é“¶è¡Œ")
    assert (item.symbol, item.exchange, item.tencent_symbol) == ("600000", "SH", "sh600000")
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_domain.py -v`  
Expected: FAIL because `assl.domain` does not exist.

- [ ] **Step 3: Implement immutable domain objects**

Use `@dataclass(frozen=True, slots=True)` and string enums for `SignalChannel`, `Grade`, and `PublicBucket`. `Instrument.from_secid()` must accept only:

- Shenzhen: `000/001/002/003/300/301` with market prefix `0`;
- Shanghai: `600/601/603/605/688/689` with market prefix `1`.

Define these public fields exactly:

```python
@dataclass(frozen=True, slots=True)
class WatchlistVersion:
    id: UUID
    created_at: datetime
    source: str
    item_count: int
    content_sha256: str
    note: str | None

@dataclass(frozen=True, slots=True)
class Coverage:
    universe_count: int
    covered_count: int
    missing_symbols: tuple[str, ...]
    source_timestamp: datetime | None
    publishable: bool

@dataclass(frozen=True, slots=True)
class RunKey:
    as_of_date: date
    watchlist_version_id: UUID
    algorithm_version_id: str

@dataclass(frozen=True, slots=True)
class RunError:
    stage: str
    summary: str

@dataclass(frozen=True, slots=True)
class Prediction:
    tier: str | None
    gap: float
    convergence_speed: float
    x1: float
    x1_change_pct: float
    projected_days: float
    valid: bool
    invalidation_reasons: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class StockSignal:
    instrument: Instrument
    as_of_date: date
    signal_date: date | None
    channel: SignalChannel
    grade: Grade
    public_bucket: PublicBucket | None
    fundamental_priority: int
    dif: float
    dea: float
    macd_hist: float
    gap: float
    convergence_speed: float | None
    x1: float | None
    x1_change_pct: float | None
    projected_days: float | None
    ma20: float | None
    ma30: float | None
    ma60: float | None
    close_vs_ma20: float | None
    close_vs_ma30: float | None
    close_vs_ma60: float | None
    volume_ratio_5_20: float | None
    bottom_divergence: bool
    top_divergence: bool
    signal_age_days: int
    dif_above_zero: bool
    histogram_improvement: float
    ma_structure_score: float
    volume_score: float
    risk_score: float
    reason: str
    confirm_price: float | None
    invalidation_price: float | None
    risk: str | None

@dataclass(frozen=True, slots=True)
class RankedScreen:
    top10: tuple[StockSignal, ...]
    p1: tuple[StockSignal, ...]
    p2: tuple[StockSignal, ...]
    risk_watch: tuple[StockSignal, ...]

@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: UUID
    as_of_date: date
    status: str
    coverage: Coverage
    result_sha256: str | None
```

`canonical_json()` must use UTF-8-preserving `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` and SHA-256 must hash the UTF-8 bytes.

- [ ] **Step 4: Run domain tests**

Run: `python -m pytest tests/test_domain.py -v`  
Expected: all pass.

- [ ] **Step 5: Commit domain types**

```bash
git add src/assl/domain.py tests/test_domain.py
git commit -m "feat: define ASSL domain types"
```

---

### Task 3: Add the Private Supabase Schema and Repository

**Files:**
- Create: `supabase/migrations/202608120001_assl_private.sql`
- Create: `src/assl/db.py`
- Create: `tests/test_migration_contract.py`
- Create: `tests/integration/test_db.py`
- Create: `pytest.ini`

**Interfaces:**
- Consumes: `Settings.database_url`, domain dataclasses
- Produces: `AsslRepository` with `transaction()`, `latest_watchlist()`, `insert_watchlist_version()`, `upsert_bars()`, `start_run()`, `finish_run()`, `insert_signal_results()`

- [ ] **Step 1: Write migration contract tests**

```python
from pathlib import Path

SQL = Path("supabase/migrations/202608120001_assl_private.sql").read_text("utf-8")

def test_private_schema_and_unique_run_contract_exist():
    assert "create schema if not exists assl_private" in SQL.lower()
    assert "unique (as_of_date, watchlist_version_id, algorithm_version_id)" in SQL.lower()
    assert "create table assl_private.watchlist_versions" in SQL.lower()
    assert "create table assl_private.signal_results" in SQL.lower()

def test_private_schema_is_not_granted_to_public_roles():
    lowered = SQL.lower()
    assert "grant usage on schema assl_private to anon" not in lowered
    assert "grant usage on schema assl_private to authenticated" not in lowered
```

- [ ] **Step 2: Verify the migration tests fail**

Run: `python -m pytest tests/test_migration_contract.py -v`  
Expected: FAIL because the migration file is absent.

- [ ] **Step 3: Write the complete core migration**

Create all tables from design sections 6.1â€“6.8, even though later plans populate snapshots and outcomes. Use this concrete migration structure:

```sql
create schema if not exists assl_private;
revoke all on schema assl_private from public, anon, authenticated;

create table assl_private.watchlist_versions (
  id uuid primary key,
  created_at timestamptz not null default now(),
  source text not null,
  item_count integer not null check (item_count > 0),
  content_sha256 text not null unique,
  note text
);
create table assl_private.watchlist_members (
  watchlist_version_id uuid not null references assl_private.watchlist_versions(id) on delete restrict,
  symbol text not null check (symbol ~ '^[0-9]{6}$'),
  name text not null,
  exchange text not null check (exchange in ('SH','SZ')),
  fundamental_priority smallint not null default 0 check (fundamental_priority between 0 and 2),
  theme_tags jsonb,
  primary key (watchlist_version_id, symbol)
);
create table assl_private.daily_bars (
  symbol text not null,
  trade_date date not null,
  open numeric not null check (open > 0), high numeric not null check (high > 0),
  low numeric not null check (low > 0), close numeric not null check (close > 0),
  volume numeric not null check (volume >= 0),
  adjustment text not null check (adjustment = 'qfq'),
  source text not null check (source = 'tencent'),
  source_timestamp timestamptz not null,
  ingested_at timestamptz not null default now(),
  primary key (symbol, trade_date, adjustment, source),
  check (high >= greatest(open, close, low)),
  check (low <= least(open, close, high))
);
create table assl_private.algorithm_versions (
  id text primary key, code_sha text not null, config jsonb not null,
  created_at timestamptz not null default now(), description text not null
);
create table assl_private.screening_runs (
  id uuid primary key, as_of_date date not null,
  watchlist_version_id uuid not null references assl_private.watchlist_versions(id) on delete restrict,
  algorithm_version_id text not null references assl_private.algorithm_versions(id) on delete restrict,
  status text not null check (status in ('running','succeeded','failed','skipped')),
  universe_count integer not null, covered_count integer not null default 0,
  coverage_ratio numeric not null default 0,
  missing_symbols jsonb not null default '[]'::jsonb,
  source_timestamp timestamptz, started_at timestamptz not null default now(),Û¯5¶‰žËkºwµçp½µ…É­•Ð½Ñ•¹•¹Ð¹Áå€(´É•…Ñ”èÍÉŒ½…ÍÍ°½µ…É­•Ð½ÅÕ…±¥Ñä¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½™¥áÑÕÉ•Ì½Ñ•¹•¹Ñ}Å™Ä¹©Í½¹€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}Ñ•¹•¹Ð¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}ÅÕ…±¥Ñä¹Áå€((¨©%¹Ñ•É™…•Ìè¨¨(´AÉ½‘Õ•ÌèQ•¹•¹Ñ±¥•¹Ð¹™•Ñ¡}‘…¥±ä¡¥¹ÍÑÉÕµ•¹Ð°ÍÑ…ÉÐ°•¹°½Õ¹Ð¤€´øÑÕÁ±•m	…È°€¸¸¹u€(´AÉ½‘Õ•ÌèQ•¹•¹Ñ±¥•¹Ð¹™•Ñ¡}µ…¹ä¡¥¹ÍÑÉÕµ•¹ÑÌ°ÕÑ½™˜°•á¥ÍÑ¥¹}±…Ñ•ÍÐ¤€´ø•Ñ¡	…Ñ¡€(´AÉ½‘Õ•ÌèÙ…±¥‘…Ñ•}‰…ÉÌ¡‰…ÉÌ°ÕÑ½™˜¤€´øÑÕÁ±•m	…È°€¸¸¹u€(´AÉ½‘Õ•Ìè…±Õ±…Ñ•}½Ù•É…”¡Õ¹¥Ù•ÉÍ”°™•Ñ¡•¤€´ø½Ù•É…•€((´lt€¨©MÑ•À€Äè]É¥Ñ”Á…ÉÍ•È…¹ÕÑ½™˜Ñ•ÍÑÌÕÍ¥¹œ„Í…Ù•É•ÍÁ½¹Í”¨¨()ÁåÑ¡½¸)‘•˜Ñ•ÍÑ}Á…ÉÍ•}Å™Å}ÁÉ•™•ÉÍ}Å™Å‘…å}…¹‘}½‰•åÍ}ÕÑ½™˜¡™¥áÑÕÉ•}©Í½¸¤è(€€€‰…ÉÌ€ôÁ…ÉÍ•}Ñ•¹•¹Ñ}Á…å±½… ‰Í ØÀÀÀÀÀˆ°™¥áÑÕÉ•}©Í½¸°ÕÑ½™˜õ‘…Ñ” ÈÀÈØ°€à°€ÄÄ¤¤(€€€…ÍÍ•ÉÐ‰…ÉÍl´Åt¹ÑÉ…‘•}‘…Ñ”€ôô‘…Ñ” ÈÀÈØ°€à°€ÄÄ¤(€€€…ÍÍ•ÉÐ…±°¡‰…È¹ÑÉ…‘•}‘…Ñ”€ðô‘…Ñ” ÈÀÈØ°€à°€ÄÄ¤™½È‰…È¥¸‰…ÉÌ¤()‘•˜Ñ•ÍÑ}Ù…±¥‘…Ñ•}‰…ÉÍ}É•©•ÑÍ}‘ÕÁ±¥…Ñ•}‘…Ñ” ¤è(€€€Ý¥Ñ ÁåÑ•ÍÐ¹É…¥Í•Ì¡…Ñ…EÕ…±¥ÑåÉÉ½È°µ…Ñ ô‰‘ÕÁ±¥…Ñ”ˆ¤è(€€€€€€€Ù…±¥‘…Ñ•}‰…ÉÌ ¡‰…È ˆÈÀÈØ´Àà´ÄÄˆ¤°‰…È ˆÈÀÈØ´Àà´ÄÄˆ¤¤°‘…Ñ” ÈÀÈØ°€à°€ÄÄ¤¤)€((´lt€¨©MÑ•À€ÈèY•É¥™ä™…¥±ÕÉ”¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}Ñ•¹•¹Ð¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÅÕ…±¥Ñä¹Áä€µÙ€€€)áÁ•Ñ•è%0‰•…ÕÍ”µ…É­•Ðµ½‘Õ±•Ì…É”…‰Í•¹Ð¸((´lt€¨©MÑ•À€Ìè%µÁ±•µ•¹ÐÉ•ÅÕ•ÍÐ…¹Á…ÉÍ”±½¥Œ¨¨()½¹ÍÑÉÕÐÉ•ÅÕ•ÍÑÌ•á…Ñ±ä…Ìè()ÁåÑ¡½¸)Á…É…µÌ€ôì‰Á…É…´ˆè˜‰í¥¹ÍÑÉÕµ•¹Ð¹Ñ•¹•¹Ñ}Íåµ‰½±ô±‘…ä±íÍÑ…ÉÐè•d´•´´•‘ô±í•¹è•d´•´´•‘ô±í½Õ¹Ñô±Å™Ä‰ô)ÕÉ°€ô€‰¡ÑÑÁÌè¼½Ý•ˆ¹¥™éÄ¹Ñ¥µœ¹¸½…ÁÁÍÑ½¬½…ÁÀ½™Å­±¥¹”½•Ðˆ)€()UÍ”¡ÑÑÁà¹±¥•¹Ð¡Ñ¥µ•½ÕÐôÈÀ¥€Ý¥Ñ Ñ¡”•á¥ÍÑ¥¹œQ•¹•¹ÐI•™•É•É€…¹„¹½Éµ…°ÕÍ•È…•¹Ð¸I•ÑÉä¹•ÑÝ½É¬•ÉÉ½ÉÌ…¹!QQ@€ÐÈä¼ÕáàÕÀÑ¼™½ÕÈÑ¥µ•ÌÝ¥Ñ ‘•±…åÌ€À¸Ü°€Ä¸Ð°€È¸à°…¹€Ô¸ØÍ•½¹‘Ì¸1¥µ¥ÐÝ½É­•È½¹ÕÉÉ•¹äÑ¼€à¸A…ÉÍ”Å™Å‘…å€™¥ÉÍÐ…¹‘…å€½¹±ä…Ì…¸•áÁ±¥¥Ñ±äÉ•½É‘•™…±±‰…¬¸((´lt€¨©MÑ•À€Ðè%µÁ±•µ•¹ÐÙ…±¥‘…Ñ¥½¸…¹½Ù•É…”‰•¡…Ù¥½È¨¨()Y…±¥‘…Ñ”…Í•¹‘¥¹œÕ¹¥ÅÕ”‘…Ñ•Ì°™¥¹¥Ñ”Á½Í¥Ñ¥Ù”=!1°¡¥ €øôµ…à¡½Á•¸°±½Í”°±½Ü¥€°±½Ü€ðôµ¥¸¡½Á•¸°±½Í”°¡¥ ¥€°¹½¹¹•…Ñ¥Ù”Ù½±Õµ”°…¹ÕÑ½™˜½µÁ±¥…¹”¸½Ù•É…”¹ÁÕ‰±¥Í¡…‰±•€¥ÌÑÉÕ”½¹±äÝ¡•¸½Ù•É•€¼Õ¹¥Ù•ÉÍ”€øô€À¸äá€¸()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}Ñ•¹•¹Ð¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÅÕ…±¥Ñä¹Áä€µÙ€€€)áÁ•Ñ•èÁ…ÍÌ¸€€)IÕ¸±¥Ù”Íµ½­”½¹±äÝ¡•¸•áÁ±¥¥Ñ±ä…ÕÑ¡½É¥é•èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½¥¹Ñ•É…Ñ¥½¸½Ñ•ÍÑ}Ñ•¹•¹Ñ}±¥Ù”¹Áä€µØ€µ´¹•ÑÝ½É­€€€)áÁ•Ñ•è½¹”­¹½Ý¸µÍ¡…É”É•ÑÕÉ¹Ì…Ð±•…ÍÐ€ØÀ½µÁ±•Ñ•Å™Ä‰…ÉÌ…¹¹¼‘…Ñ”‰•å½¹ÕÑ½™˜¸((´lt€¨©MÑ•À€Ôè½µµ¥Ð¥¹•ÍÑ¥½¸¨¨()‰…Í )¥Ð…‘ÍÉŒ½…ÍÍ°½µ…É­•ÐÑ•ÍÑÌ½™¥áÑÕÉ•Ì½Ñ•¹•¹Ñ}Å™Ä¹©Í½¸Ñ•ÍÑÌ½Ñ•ÍÑ}Ñ•¹•¹Ð¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÅÕ…±¥Ñä¹Áä)¥Ð½µµ¥Ð€µ´€‰™•…Ðè…‘Q•¹•¹ÐÅ™Ä¥¹•ÍÑ¥½¸ˆ)€((´´´((ŒŒŒQ…Í¬€ØèA½ÉÐ%¹‘¥…Ñ½ÈAÉ¥µ¥Ñ¥Ù•ÌÝ¥Ñ I•É•ÍÍ¥½¸¥áÑÕÉ•Ì((¨©¥±•Ìè¨¨(´É•…Ñ”èÍÉŒ½…ÍÍ°½Í¥¹…±Ì½}}¥¹¥Ñ}|¹Áå€(´É•…Ñ”èÍÉŒ½…ÍÍ°½Í¥¹…±Ì½¥¹‘¥…Ñ½ÉÌ¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½™¥áÑÕÉ•Ì½¥¹‘¥…Ñ½É}‰…ÉÌ¹ÍÙ€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}¥¹‘¥…Ñ½ÉÌ¹Áå€((¨©%¹Ñ•É™…•Ìè¨¨(´AÉ½‘Õ•Ìè…‘‘}¥¹‘¥…Ñ½ÉÌ¡™É…µ”°½¹™¥œ¤€´øÁ¹…Ñ…É…µ•€(´AÉ½‘Õ•ÌèÉ½ÍÍ•‘}ÕÀ¡„°ˆ°±½½­‰…¬¤€´øÑÕÁ±•m¥¹Ð°€¸¸¹u€(´AÉ½‘Õ•ÌèÍÑÉ•¹Ñ¡•¹¥¹}¥¹Ñ•ÉÙ…±Ì¡¡¥ÍÐ°µ…á¥µÕ´ôÌ¤€´ø¥¹Ñ€((´lt€¨©MÑ•À€ÄèÉ•…Ñ”„™¥á•=!1X™¥áÑÕÉ”…¹•áÁ•Ñ•Ù…±Õ•Ì¨¨()•¹•É…Ñ”¥¹‘¥…Ñ½É}‰…ÉÌ¹ÍÙ€Ý¥Ñ €àÀÉ½ÝÌÝ¡•É”±½Í”¥Ì€ÄÀÀ€¬¤¨À¸È€¬€ ¡¤€”€Ü¤´Ì¤¨À¸Å€…¹Ù½±Õµ”¥Ì€ÄÀÀÀ€¬€¡¤€”€Ô¤¨ÄÀÁ€ìÍ•Ð½Á•¸•ÅÕ…°Ñ¼±½Í”°¡¥ Ñ¼±½Í”€¬€À¸Ô°…¹±½ÜÑ¼±½Í”€´€À¸Ô¸Q¡”™É½é•¸™¥¹…°•áÁ•Ñ•Ù…±Õ•Ì…É”%€Ä¸ÌÜÔäÐÔÌàØÜÌÕ€°€Ä¸ÌäÀÀäàÜÀÐÐÐå€°5¡¥ÍÑ½É…´€´À¸ÀÈàÌÀØØÌÔÐÈá€°5ÈÀ€ÄÄÌ¸å€°5ÌÀ€ÄÄÈ¸àå€°5ØÀ€ÄÀä¸àäÕ€°…¹Ù½±Õµ”É…Ñ¥¼€Ä¸Á€¸()ÁåÑ¡½¸)‘•˜Ñ•ÍÑ}¥¹‘¥…Ñ½É}™¥áÑÕÉ•}µ…Ñ¡•Í}™É½é•¹}Ù…±Õ•Ì ¤è(€€€™É…µ”€ôÁ¹É•…‘}ÍØ¡%aQUI°Á…ÉÍ•}‘…Ñ•Ìõl‰‘…Ñ”‰t¤(€€€½ÕÐ€ô…‘‘}¥¹‘¥…Ñ½ÉÌ¡™É…µ”°±½É¥Ñ¡µ½¹™¥œ¹µ…‘}ØÄ ¤¤(€€€±…ÍÐ€ô½ÕÐ¹¥±½l´Åt(€€€…ÍÍ•ÉÐ±…ÍÑl‰‘¥˜‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à Ä¸ÌÜÔäÐÔÌàØÜÌÔ°…‰ÌôÅ”´Ø¤(€€€…ÍÍ•ÉÐ±…ÍÑl‰‘•„‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à Ä¸ÌäÀÀäàÜÀÐÐÐä°…‰ÌôÅ”´Ø¤(€€€…ÍÍ•ÉÐ±…ÍÑl‰µ…‘}¡¥ÍÐ‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à ´À¸ÀÈàÌÀØØÌÔÐÈà°…‰ÌôÅ”´Ø¤(€€€…ÍÍ•ÉÐ±…ÍÑl‰µ„ÈÀ‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à ÄÄÌ¸ä°…‰ÌôÅ”´Ø¤(€€€…ÍÍ•ÉÐ±…ÍÑl‰µ„ÌÀ‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à ÄÄÈ¸àä°…‰ÌôÅ”´Ø¤(€€€…ÍÍ•ÉÐ±…ÍÑl‰µ„ØÀ‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à ÄÀä¸àäÔ°…‰ÌôÅ”´Ø¤(€€€…ÍÍ•ÉÐ±…ÍÑl‰Ù½±Õµ•}É…Ñ¥½|Õ|ÈÀ‰t€ôôÁåÑ•ÍÐ¹…ÁÁÉ½à Ä¸À°…‰ÌôÅ”´Ø¤)€((´lt€¨©MÑ•À€ÈèY•É¥™ä™…¥±ÕÉ”‰•™½É”¥µÁ±•µ•¹Ñ…Ñ¥½¸¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}¥¹‘¥…Ñ½ÉÌ¹Áä€µÙ€€€)áÁ•Ñ•è%0‰•…ÕÍ”¥¹‘¥…Ñ½È™Õ¹Ñ¥½¹Ì…É”…‰Í•¹Ð¸((´lt€¨©MÑ•À€Ìè%µÁ±•µ•¹Ð¥¹‘¥…Ñ½ÉÌÝ¥Ñ¡½ÕÐÑ¡¥ÉµÁ…ÉÑäQ±¥‰É…É¥•Ì¨¨()UÍ”Á…¹‘…Ì]4•á…Ñ±äè()ÁåÑ¡½¸)•µ„ÄÈ€ô±½Í”¹•Ý´¡ÍÁ…¸ôÄÈ°…‘©ÕÍÐõ…±Í”¤¹µ•…¸ ¤)•µ„ÈØ€ô±½Í”¹•Ý´¡ÍÁ…¸ôÈØ°…‘©ÕÍÐõ…±Í”¤¹µ•…¸ ¤)‘¥˜€ô•µ„ÄÈ€´•µ„ÈØ)‘•„€ô‘¥˜¹•Ý´¡ÍÁ…¸ôä°…‘©ÕÍÐõ…±Í”¤¹µ•…¸ ¤)µ…‘}¡¥ÍÐ€ô€È€¨€¡‘¥˜€´‘•„¤)€()5Ì…É”Í¥µÁ±”É½±±¥¹œµ•…¹Ì¸Y½±Õµ”É…Ñ¥¼¥ÌÑ¡”±…Ñ•ÍÐ€ÔµÍ•ÍÍ¥½¸µ•…¸‘¥Ù¥‘•‰äÑ¡”±…Ñ•ÍÐ€ÈÀµÍ•ÍÍ¥½¸µ•…¸¸-••À™Õ±°µÁÉ•¥Í¥½¸¥¹Ñ•É¹…°Ù…±Õ•Ì…¹É½Õ¹½¹±ä‘ÕÉ¥¹œÁ•ÉÍ¥ÍÑ•¹”½•áÁ½ÉÐ¸((´lt€¨©MÑ•À€ÐèIÕ¸É•É•ÍÍ¥½¸…¹ÁÉ½Á•ÉÑäÑ•ÍÑÌ¨¨()‘Ñ•ÍÑÌÑ¡…Ð„½¹ÍÑ…¹Ð±½Í”Í•É¥•Ìå¥•±‘Ìé•É¼%½½¡¥ÍÐ…™Ñ•È¥¹¥Ñ¥…±¥é…Ñ¥½¸°É½ÍÍ¥¹œ¡•±Á•ÉÌ‘¼¹½ÐÉ•Á½ÉÐ…¸•Ù•¹Ð‰•™½É”‰½Ñ Á½¥¹ÑÌ•á¥ÍÐ°…¹ÍÑÉ•¹Ñ¡•¹¥¹œ½Õ¹ÑÌ¹¼µ½É”Ñ¡…¸Ñ¡É•”¥¹Ñ•ÉÙ…±Ì¸()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}¥¹‘¥…Ñ½ÉÌ¹Áä€µÙ€€€)áÁ•Ñ•è…±°Á…ÍÌ¸((´lt€¨©MÑ•À€Ôè½µµ¥Ð¥¹‘¥…Ñ½È•¹¥¹”¨¨()‰…Í )¥Ð…‘ÍÉŒ½…ÍÍ°½Í¥¹…±ÌÑ•ÍÑÌ½™¥áÑÕÉ•Ì½¥¹‘¥…Ñ½É}‰…ÉÌ¹ÍØÑ•ÍÑÌ½Ñ•ÍÑ}¥¹‘¥…Ñ½ÉÌ¹Áä)¥Ð½µµ¥Ð€µ´€‰™•…Ðè…‘‘•Ñ•Éµ¥¹¥ÍÑ¥Œ5¥¹‘¥…Ñ½ÉÌˆ)€((´´´((ŒŒŒQ…Í¬€Üè%µÁ±•µ•¹Ð…ÕÍ…°¥Ù•É•¹”…¹AÉ•‘¥Ñ¥Ù”É½ÍÌ((¨©¥±•Ìè¨¨(´É•…Ñ”èÍÉŒ½…ÍÍ°½Í¥¹…±Ì½‘¥Ù•É•¹”¹Áå€(´É•…Ñ”èÍÉŒ½…ÍÍ°½Í¥¹…±Ì½ÁÉ•‘¥Ñ¥Ù”¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}‘¥Ù•É•¹”¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}ÁÉ•‘¥Ñ¥Ù”¹Áå€((¨©%¹Ñ•É™…•Ìè¨¨(´½¹ÍÕµ•Ìè¥¹‘¥…Ñ½Èµ•¹É¥¡•…Ñ…É…µ”(´AÉ½‘Õ•Ìè½¹™¥Éµ•‘}Á¥Ù½ÑÌ¡Í•É¥•Ì°­¥¹°Ý¥¹‘½ÜôÈ°…Í}½™}¥¹‘•àõ9½¹”¤€´øÑÕÁ±•m¥¹Ð°€¸¸¹u€(´AÉ½‘Õ•Ìè™¥¹‘}‘¥Ù•É•¹”¡™É…µ”°­¥¹°±½½­‰…¬ôØÀ¤€´ø¥Ù•É•¹”ð9½¹•€(´AÉ½‘Õ•Ìè¹•áÑ}É½ÍÍ}ÁÉ¥”¡•µ„ÄÈ°•µ„ÈØ°‘•„¤€´ø™±½…Ñ€(´AÉ½‘Õ•Ìè•Ù…±Õ…Ñ•}ÁÉ•‘¥Ñ¥½¸¡™É…µ”°Ñ½Á}‘¥Ù•É•¹•}É¥Í¬¤€´øAÉ•‘¥Ñ¥½¹€((´lt€¨©MÑ•À€Äè]É¥Ñ”¹¼µ™ÕÑÕÉ”µ‘…Ñ„‘¥Ù•É•¹”Ñ•ÍÑÌ¨¨()ÁåÑ¡½¸)‘•˜Ñ•ÍÑ}Á¥Ù½Ñ}¥Í}¹½Ñ}Ù¥Í¥‰±•}Õ¹Ñ¥±}É¥¡Ñ}Ý¥¹‘½Ý}•á¥ÍÑÌ ¤è(€€€Ù…±Õ•Ì€ôÁ¹M•É¥•Ì¡lÄÀ°€ä°€à°€ä°€ÄÁt¤(€€€…ÍÍ•ÉÐ½¹™¥Éµ•‘}Á¥Ù½ÑÌ¡Ù…±Õ•Ì¹¥±½lèÍt°€‰±½Üˆ°Ý¥¹‘½ÜôÈ¤€ôô€ ¤(€€€…ÍÍ•ÉÐ½¹™¥Éµ•‘}Á¥Ù½ÑÌ¡Ù…±Õ•Ì°€‰±½Üˆ°Ý¥¹‘½ÜôÈ¤€ôô€ È°¤()‘•˜Ñ•ÍÑ}‰½ÑÑ½µ}‘¥Ù•É•¹•}É•ÅÕ¥É•Í}Í•½¹‘}ÁÉ¥•}±½Ý}…¹‘}¡¥¡•É}‘¥˜ ¤è(€€€É•ÍÕ±Ð€ô™¥¹‘}‘¥Ù•É•¹”¡‰½ÑÑ½µ}™¥áÑÕÉ” ¤°€‰‰½ÑÑ½´ˆ°±½½­‰…¬ôØÀ¤(€€€…ÍÍ•ÉÐÉ•ÍÕ±Ð¹½¹™¥Éµ•¥ÌQÉÕ”(€€€…ÍÍ•ÉÐÉ•ÍÕ±Ð¹Í•½¹‘}ÁÉ¥”€ðôÉ•ÍÕ±Ð¹™¥ÉÍÑ}ÁÉ¥”€¨€Ä¸ÀÄ(€€€…ÍÍ•ÉÐÉ•ÍÕ±Ð¹Í•½¹‘}¥¹‘¥…Ñ½È€øÉ•ÍÕ±Ð¹™¥ÉÍÑ}¥¹‘¥…Ñ½È)€((´lt€¨©MÑ•À€Èè]É¥Ñ”ÁÉ•‘¥Ñ¥Ù”µÉ½ÍÌÑ•ÍÑÌ™É½´Ñ¡”±•…äÙ•É¥™¥•…Í•Ì¨¨()A½ÉÐÑ¡”É••¸µ¡¥ÍÑ½É…´…¹É•µ¡¥ÍÑ½É…´…Í•Ì™É½´É•…µ½¹±äÑ•ÍÑ}ÍÉ••¹}Ý…Ñ¡±¥ÍÑ}µ…‘}ÁÉ•‘¥Ñ¥Ù”¹Áå€¸ÍÍ•ÉÐè((´•á…Ð`Ä¥¹Ù•ÉÍ¥½¸Ý¥Ñ¡¥¸€Å”´Ù€ì(´@Ä…ÐÁÉ½©•Ñ•‘}‘…åÌ€ðô€Ä¸Õ€…¹àÄ€ðô±½Í”€¨€Ä¸ÀÄÕ€ì(´@È…ÐÁÉ½©•Ñ•‘}‘…åÌ€ðô€Í€…¹àÄ€ðô±½Í”€¨€Ä¸ÀÍ€ì(´¹¼Ñ¥•ÈÝ¡•¸…À•áÁ…¹‘Ì°%™…±±Ì°Ù½±Õµ”É…Ñ¥¼¥Ì‰•±½Ü€À¸ÜÀ°ÁÉ¥”¥Ì‰•±½Ü5ÈÀ€¨€À¸äÝ€°5ÈÀÍ¥¹¥™¥…¹Ñ±ä‘•Ñ•É¥½É…Ñ•Ì°½ÈÑ½Àµ‘¥Ù•É•¹”É¥Í¬¥ÌÑÉÕ”¸((´lt€¨©MÑ•À€ÌèY•É¥™ä‰½Ñ ÍÕ¥Ñ•Ì™…¥°¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}‘¥Ù•É•¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÁÉ•‘¥Ñ¥Ù”¹Áä€µÙ€€€)áÁ•Ñ•è%0‰•…ÕÍ”¥µÁ±•µ•¹Ñ…Ñ¥½¹Ì…É”…‰Í•¹Ð¸((´lt€¨©MÑ•À€Ðè%µÁ±•µ•¹Ð…ÕÍ…°‘¥Ù•É•¹”…¹•á…Ð`Äµ…Ñ ¨¨()UÍ”Ñ¡”ÑÝ¼µÍ¥‘•Á¥Ù½ÐÝ¥¹‘½Ü½¹±ä…™Ñ•ÈÑ¡”É¥¡ÐµÍ¥‘”Í…µÁ±•Ì•á¥ÍÐ¸M•…É Á…¥ÉÌ€×ŠLÌÀÍ•ÍÍ¥½¹Ì…Á…ÉÐ¥¹Í¥‘”Ñ¡”±…ÍÐ€ØÀÍ•ÍÍ¥½¹Ì…¹¡½½Í”Ñ¡”¹•Ý•ÍÐÙ…±¥Á…¥È°‰É•…­¥¹œÑ¥•Ì‰äÍÑÉ½¹•È¥¹‘¥…Ñ½È¥µÁÉ½Ù•µ•¹Ð¸()½È`Ä°Í½±Ù”Ñ¡”¹•áÐµÍÑ•À5•ÅÕ…Ñ¥½¹Ì…±•‰É…¥…±±äÉ…Ñ¡•ÈÑ¡…¸ÕÍ¥¹œ„ÁÉ¥”É¥¸Y…±¥‘…Ñ”Ñ¡”É•ÍÕ±Ð‰äÍÕ‰ÍÑ¥ÑÕÑ¥¹œ`Ä‰…¬¥¹Ñ¼¹•áÐ%½…¹…ÍÍ•ÉÑ¥¹œ¹•áÑ}‘¥˜€øô¹•áÑ}‘•…€Ý¥Ñ¡¥¸€Å”´ÄÁ€¸()AÉ•‘¥Ñ¥½¸¥¹Ù…±¥‘…Ñ¥½¸É•…Í½¹ÌµÕÍÐ‰”ÍÑ…‰±”½‘•Ìè()ÁåÑ¡½¸( ‰…Á}¹½Ñ}Í¡É¥¹­¥¹œˆ°€‰É••¹}¡¥ÍÑ}¹½Ñ}Í¡½ÉÑ•¹¥¹œˆ°€‰‘¥™}¹½Ñ}É¥Í¥¹œˆ°(€‰½¹Ù•É•¹•}Ñ½½}Í±½Üˆ°€‰‰•±½Ý}µ„ÈÁ}™±½½Èˆ°€‰µ„ÈÁ}‘•Ñ•É¥½É…Ñ¥¹œˆ°(€‰±½Ý}Ù½±Õµ”ˆ°€‰Ñ½Á}‘¥Ù•É•¹•}É¥Í¬ˆ¤)€((´lt€¨©MÑ•À€ÔèIÕ¸Ñ•ÍÑÌ…¹½µÁ…É”……¥¹ÍÐ±•…ä½ÕÑÁÕÑÌ¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}‘¥Ù•É•¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÁÉ•‘¥Ñ¥Ù”¹Áä€µÙ€€€)áÁ•Ñ•èÁ…ÍÌ¸€€)IÕ¸…¸½™™±¥¹”½µÁ…É¥Í½¸……¥¹ÍÐÑ¡”€ÈÀÈØ´Àà´ÄÀ±•…ä…¡”…¹…ÍÍ•ÉÐ…±°ÁÉ•Ù¥½ÕÍ±äÙ•É¥™¥•@Ä½@È…Í•ÌÉ•Ñ…¥¸Ñ¡”Í…µ”Ñ¥•È…¹`ÄÝ¥Ñ¡¥¸€Å”´Ñ€¸((´lt€¨©MÑ•À€Øè½µµ¥ÐÍ¥¹…°µ…Ñ ¨¨()‰…Í )¥Ð…‘ÍÉŒ½…ÍÍ°½Í¥¹…±Ì½‘¥Ù•É•¹”¹ÁäÍÉŒ½…ÍÍ°½Í¥¹…±Ì½ÁÉ•‘¥Ñ¥Ù”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}‘¥Ù•É•¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÁÉ•‘¥Ñ¥Ù”¹Áä)¥Ð½µµ¥Ð€µ´€‰™•…Ðè…‘‘¥Ù•É•¹”…¹ÁÉ•‘¥Ñ¥Ù”É½ÍÌÍ¥¹…±Ìˆ)€((´´´((ŒŒŒQ…Í¬€àè±…ÍÍ¥™ä°É…‘”°…¹I…¹¬M¥¹…±Ì•Ñ•Éµ¥¹¥ÍÑ¥…±±ä((¨©¥±•Ìè¨¨(´É•…Ñ”èÍÉŒ½…ÍÍ°½Í¥¹…±Ì½±…ÍÍ¥™ä¹Áå€(´É•…Ñ”èÍÉŒ½…ÍÍ°½É…¹­¥¹œ¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}±…ÍÍ¥™ä¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}É…¹­¥¹œ¹Áå€((¨©%¹Ñ•É™…•Ìè¨¨(´AÉ½‘Õ•Ìè±…ÍÍ¥™å}ÍÑ½¬¡¥¹ÍÑÉÕµ•¹Ð°™É…µ”°™Õ¹‘…µ•¹Ñ…±}ÁÉ¥½É¥Ñä°½¹™¥œ¤€´øMÑ½­M¥¹…±€(´AÉ½‘Õ•ÌèÉ…¹­}ÍÉ••¸¡Í¥¹…±Ì°±¥µ¥ÐôÄÀ°É¥Í­}±¥µ¥ÐôÔ¤€´øI…¹­•‘MÉ••¹€((´lt€¨©MÑ•À€Äè]É¥Ñ”Ñ…‰±”µ‘É¥Ù•¸É…‘”Ñ•ÍÑÌ¨¨()ÁåÑ¡½¸)ÁåÑ•ÍÐ¹µ…É¬¹Á…É…µ•ÑÉ¥é”  ‰‰½ÑÑ½´ˆ°€‰É½ÍÌˆ°€‰Ñ¥•Èˆ°€‰•áÑÉ…Ìˆ°€‰É…‘”ˆ¤°l(€€€€¡QÉÕ”°QÉÕ”°9½¹”°€Ì°É…‘”¹MQI=9}L¤°(€€€€¡QÉÕ”°QÉÕ”°9½¹”°€À°É…‘”¹L¤°(€€€€¡QÉÕ”°…±Í”°€‰@Äˆ°€À°É…‘”¹}A1UL¤°(€€€€¡QÉÕ”°…±Í”°€‰@Èˆ°€À°É…‘”¹¤°(€€€€¡…±Í”°QÉÕ”°9½¹”°€À°É…‘”¹	}A1UL¤°(€€€€¡…±Í”°…±Í”°€‰@Äˆ°€À°É…‘”¹¤°)t¤)‘•˜Ñ•ÍÑ}É…‘•}µ…ÑÉ¥à¡‰½ÑÑ½´°É½ÍÌ°Ñ¥•È°•áÑÉ…Ì°É…‘”¤è(€€€…ÍÍ•ÉÐ¡½½Í•}É…‘”¡‰½ÑÑ½´°É½ÍÌ°Ñ¥•È°•áÑÉ…Ì¤¥ÌÉ…‘”)€()‘„Ñ•ÍÐÑ¡…Ð„É••¹ÐÑ½À‘¥Ù•É•¹”™½É•ÌÉ¥Í­}Ý…Ñ¡€…¹•á±Õ‘•ÌÑ¡”É½Ü™É½´Ñ½ÀÄÁ€¸((´lt€¨©MÑ•À€Èè]É¥Ñ”‘•Ñ•Éµ¥¹¥ÍÑ¥ŒÉ…¹­¥¹œÑ•ÍÑÌ¨¨()É•…Ñ”Í¡Õ™™±•½Á¥•Ì½˜Ñ¡”Í…µ”Í¥¹…±Ì…¹…ÍÍ•ÉÐ¥‘•¹Ñ¥…°Íåµ‰½°½É‘•È¸ÍÍ•ÉÐÁÉ¥½É¥Ñä€ÈÁÉ••‘•ÌÁÉ¥½É¥Ñä€ÄÝ¥Ñ¡¥¸½µÁ…Ñ¥‰±”Á½Í¥Ñ¥Ù”…¹‘¥‘…Ñ•ÌìÝ¥Ñ¡¥¸•ÅÕ…°ÁÉ¥½É¥ÑäÕÍ”É…‘”°™É•Í¡¹•ÍÌ°é•É¼µ…á¥ÌÍÑ…Ñ”°¡¥ÍÑ½É…´¥µÁÉ½Ù•µ•¹Ð°5ÍÑÉÕÑÕÉ”°Ù½±Õµ”°É¥Í¬°Ñ¡•¸Íåµ‰½°…Í•¹‘¥¹œ¸((´lt€¨©MÑ•À€ÌèY•É¥™ä™…¥±ÕÉ”¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}±…ÍÍ¥™ä¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}É…¹­¥¹œ¹Áä€µÙ€€€)áÁ•Ñ•è%0‰•…ÕÍ”±…ÍÍ¥™¥…Ñ¥½¸…¹É…¹­¥¹œµ½‘Õ±•Ì…É”…‰Í•¹Ð¸((´lt€¨©MÑ•À€Ðè%µÁ±•µ•¹Ð¡…¹¹•°±…ÍÍ¥™¥…Ñ¥½¸…¹ÍÑ…‰±”Í½ÉÐ­•åÌ¨¨()•™¥¹”„ÑÕÁ±”Í½ÉÐ­•äÉ…Ñ¡•ÈÑ¡…¸‘•Á•¹‘¥¹œ½¸µÕÑ…‰±”…Ñ…É…µ”½É‘•Èè()ÁåÑ¡½¸)­•ä€ô€ (€€€€µÍ¥¹…°¹™Õ¹‘…µ•¹Ñ…±}ÁÉ¥½É¥Ñä°(€€€I}=IImÍ¥¹…°¹É…‘•t°(€€€Í¥¹…°¹Í¥¹…±}…•}‘…åÌ°(€€€€µ¥¹Ð¡Í¥¹…°¹‘¥™}…‰½Ù•}é•É¼¤°(€€€€µÍ¥¹…°¹¡¥ÍÑ½É…µ}¥µÁÉ½Ù•µ•¹Ð°(€€€€µÍ¥¹…°¹µ…}ÍÑÉÕÑÕÉ•}Í½É”°(€€€€µÍ¥¹…°¹Ù½±Õµ•}Í½É”°(€€€Í¥¹…°¹É¥Í­}Í½É”°(€€€Í¥¹…°¹¥¹ÍÑÉÕµ•¹Ð¹Íåµ‰½°°(¤)€()MÑ½É”Ñ¡”•á…ÐÝ•¥¡ÑÌ…¹É…‘”½É‘•È¥¸±½É¥Ñ¡µ½¹™¥€Í•É¥…±¥é…Ñ¥½¸¸Íåµ‰½°½ÕÁ¥•Ì½¹±ä¥ÑÌ¡¥¡•ÍÐ‰Õ­•Ð¸É¥Í­}Ý…Ñ¡€½¹Ñ…¥¹ÌÉ••¹ÐÑ½À‘¥Ù•É•¹”…¹¥¹Ù…±¥‘…Ñ•™½Éµ•É±äÁ½Í¥Ñ¥Ù”Í¥¹…±Ì°…ÁÁ•…Ð€Ô¸((´lt€¨©MÑ•À€ÔèIÕ¸±…ÍÍ¥™¥…Ñ¥½¸½É…¹­¥¹œ…¹™Õ±°Í¥¹…°Ñ•ÍÑÌ¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}±…ÍÍ¥™ä¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}É…¹­¥¹œ¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}¥¹‘¥…Ñ½ÉÌ¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}‘¥Ù•É•¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}ÁÉ•‘¥Ñ¥Ù”¹Áä€µÙ€€€)áÁ•Ñ•èÁ…ÍÌ¸((´lt€¨©MÑ•À€Øè½µµ¥Ð±…ÍÍ¥™¥…Ñ¥½¸…¹É…¹­¥¹œ¨¨()‰…Í )¥Ð…‘ÍÉŒ½…ÍÍ°½Í¥¹…±Ì½±…ÍÍ¥™ä¹ÁäÍÉŒ½…ÍÍ°½É…¹­¥¹œ¹ÁäÍÉŒ½…ÍÍ°½½¹™¥œ¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}±…ÍÍ¥™ä¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}É…¹­¥¹œ¹Áä)¥Ð½µµ¥Ð€µ´€‰™•…Ðè±…ÍÍ¥™ä…¹É…¹¬MM0Í¥¹…±Ìˆ)€((´´´((ŒŒŒQ…Í¬€äè	Õ¥±Ñ¡”%‘•µÁ½Ñ•¹Ð…¥±äA¥Á•±¥¹”…¹1$((¨©¥±•Ìè¨¨(´É•…Ñ”èÍÉŒ½…ÍÍ°½Á¥Á•±¥¹”¹Áå€(´5½‘¥™äèÍÉŒ½…ÍÍ°½±¤¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½™…­•Ì¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}Á¥Á•±¥¹”¹Áå€(´É•…Ñ”èÑ•ÍÑÌ½Ñ•ÍÑ}±¤¹Áå€((¨©%¹Ñ•É™…•Ìè¨¨(´½¹ÍÕµ•ÌèÍÍ±I•Á½Í¥Ñ½Éå€°Q•¹•¹Ñ±¥•¹Ñ€°±½É¥Ñ¡µ½¹™¥€(´AÉ½‘Õ•Ìè…¥±åA¥Á•±¥¹”¹ÉÕ¸¡…Í}½™}‘…Ñ”è‘…Ñ”ð9½¹”¤€´øIÕ¹MÕµµ…Éå€(´1$è…ÍÍ°ÉÕ¸µ‘…¥±äl´µ…Ìµ½˜eeedµ54µtl´µ½™™±¥¹•u€((´lt€¨©MÑ•À€Äè]É¥Ñ”Á¥Á•±¥¹”Ñ•ÍÑÌÝ¥Ñ ¥¸µµ•µ½Éä™…­•Ì¨¨()ÁåÑ¡½¸)‘•˜Ñ•ÍÑ}ÉÕ¹}ÕÍ•Í}±…ÍÑ}½µÁ±•Ñ•‘}‘…Ñ•}…¹‘}¥Í}¥‘•µÁ½Ñ•¹Ð¡™É½é•¹}±½¬°™…­•}É•Á¼°™…­•}µ…É­•Ð¤è(€€€Á¥Á•±¥¹”€ô…¥±åA¥Á•±¥¹”¡™…­•}É•Á¼°™…­•}µ…É­•Ð°±½É¥Ñ¡µ½¹™¥œ¹µ…‘}ØÄ ¤°±½¬õ™É½é•¹}±½¬¤(€€€™¥ÉÍÐ€ôÁ¥Á•±¥¹”¹ÉÕ¸ ¤(€€€Í•½¹€ôÁ¥Á•±¥¹”¹ÉÕ¸ ¤(€€€…ÍÍ•ÉÐ™¥ÉÍÐ¹…Í}½™}‘…Ñ”€ôô‘…Ñ” ÈÀÈØ°€à°€ÄÄ¤(€€€…ÍÍ•ÉÐÍ•½¹¹ÉÕ¹}¥€ôô™¥ÉÍÐ¹ÉÕ¹}¥(€€€…ÍÍ•ÉÐ™…­•}É•Á¼¹ÉÕ¹}½Õ¹Ð€ôô€Ä()‘•˜Ñ•ÍÑ}±½Ý}½Ù•É…•}™…¥±Í}Ý¥Ñ¡½ÕÑ}ÁÕ‰±¥Í¡¥¹œ¡™…­•}É•Á¼°™…­•}µ…É­•Ñ|äÝÁÐ¤è(€€€ÍÕµµ…Éä€ô…¥±åA¥Á•±¥¹”¡™…­•}É•Á¼°™…­•}µ…É­•Ñ|äÝÁÐ°±½É¥Ñ¡µ½¹™¥œ¹µ…‘}ØÄ ¤¤¹ÉÕ¸¡‘…Ñ” ÈÀÈØ°€à°€ÄÄ¤¤(€€€…ÍÍ•ÉÐÍÕµµ…Éä¹ÍÑ…ÑÕÌ€ôô€‰™…¥±•ˆ(€€€…ÍÍ•ÉÐ™…­•}É•Á¼¹Í¥¹…±}É•ÍÕ±Ñ}½Õ¹Ð€ôô€À)€((´lt€¨©MÑ•À€ÈèY•É¥™ä™…¥±ÕÉ”¨¨()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}Á¥Á•±¥¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}±¤¹Áä€µÙ€€€)áÁ•Ñ•è%0‰•…ÕÍ”…¥±åA¥Á•±¥¹•€¥Ì…‰Í•¹Ð¸((´lt€¨©MÑ•À€Ìè%µÁ±•µ•¹Ð½É¡•ÍÑÉ…Ñ¥½¸Ý¥Ñ •áÁ±¥¥ÐÍÑ…•Ì¨¨()MÑ…•Ì…É”ÍÑ…‰±”ÍÑÉ¥¹ÌèÉ•Í½±Ù•}‘…Ñ•€°±½…‘}Ý…Ñ¡±¥ÍÑ€°™•Ñ¡}‰…ÉÍ€°Ù…±¥‘…Ñ•}‘…Ñ…€°½µÁÕÑ•}Í¥¹…±Í€°É…¹­€°Á•ÉÍ¥ÍÑ€¸Q¡”Á¥Á•±¥¹”µÕÍÐè((Ä¸É•Í½±Ù”Ñ¡”±…Ñ•ÍÐ½µÁ±•Ñ•µÍ¡…É”Í•ÍÍ¥½¸™É½´…Ù…¥±…‰±”‘…¥±ä‰…ÉÌ…¹¡¥¹„Ñ¥µ”ì(È¸É•ÑÕÉ¸Í­¥ÁÁ•‘€Ý¡•¸¹¼¹•Ý•È½µÁ±•Ñ•Í•ÍÍ¥½¸•á¥ÍÑÌì(Ì¸¡•¬Ñ¡”ÉÕ¸Õ¹¥ÅÕ”­•ä‰•™½É”™•Ñ¡¥¹œì(Ð¸™•Ñ …¹Á•ÉÍ¥ÍÐ‰…ÉÌ¥¸‰…Ñ¡•Ìì(Ô¸ÍÑ½À‰•™½É”Í¥¹…°Á•ÉÍ¥ÍÑ•¹”¥˜½Ù•É…”¥Ì‰•±½Ü€À¸äàì(Ø¸…±Õ±…Ñ”•Ù•Éä½Ù•É•µ•µ‰•Èì(Ü¸Á•ÉÍ¥ÍÐ…±°ÁÉ¥Ù…Ñ”Í¥¹…±Ì…¹Ñ¡”É…¹­•É•ÍÕ±Ð¥¸½¹”ÑÉ…¹Í…Ñ¥½¸ì(à¸µ…É¬™…¥±ÕÉ”Ý¥Ñ ÍÑ…”…¹„Í…¹¥Ñ¥é•ÍÕµµ…Éä½¸•á•ÁÑ¥½¹Ì¸()€´µ½™™±¥¹•€™½É‰¥‘Ì¹•ÑÝ½É¬…±±Ì…¹É•ÅÕ¥É•Ì•¹½Õ …¡•‰…ÉÌ¸€´µ…Ìµ½™€…¹¹½Ð•á••Ñ¡”±…Ñ•ÍÐ½µÁ±•Ñ•‘…Ñ”¸((´lt€¨©MÑ•À€Ðè‘„½µÁ±•Ñ”½™™±¥¹”•¹µÑ¼µ•¹™¥áÑÕÉ”¨¨()UÍ”€ÄÈÍå¹Ñ¡•Ñ¥Œ¥¹ÍÑÉÕµ•¹ÑÌÝ¥Ñ €ÄÈÀ¬‰…ÉÌ•… °‘•±¥‰•É…Ñ•±äÉ•…Ñ¥¹œMÑÉ½¹L°L°¬°°¬°°@È°¹•ÕÑÉ…°°Ñ½Àµ‘¥Ù•É•¹”°¥¹Ù…±¥‘…Ñ•°…¹µ¥ÍÍ¥¹œµ‘…Ñ„…Í•Ì¸ÍÍ•ÉÐ•á…ÐQ½À€ÄÀÍåµ‰½±Ì°@Ä½@Èµ•µ‰•ÉÍ¡¥À°É¥Í¬µÝ…Ñ µ•µ‰•ÉÍ¡¥À°½Ù•É…”°…¹ÍÑ…‰±”É•ÍÕ±Ð¡…Í ¸()IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½Ñ•ÍÑ}Á¥Á•±¥¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}±¤¹Áä€µÙ€€€)áÁ•Ñ•èÁ…ÍÌ¸€€)IÕ¸èÁåÑ¡½¸€µ´ÁåÑ•ÍÐ€µ´€‰¹½Ð¥¹Ñ•É…Ñ¥½¸…¹¹½Ð¹•ÑÝ½É¬ˆ€´µ½Øõ…ÍÍ°€´µ½ØµÉ•Á½ÉÐõÑ•É´µµ¥ÍÍ¥¹€€€)áÁ•Ñ•èÁ…ÍÌÝ¥Ñ …Ð±•…ÍÐ€äÀ”½Ù•É…”™½ÈÍ¥¹…±Í€°É…¹­¥¹€°Ý…Ñ¡±¥ÍÑ€°…¹µ…É­•Ð½ÅÕ…±¥Ñå€¸((´lt€¨©MÑ•À€ÔèIÕ¸„ÁÉ¥Ù…Ñ”½™™±¥¹”É•É•ÍÍ¥½¸……¥¹ÍÐ€ÈÀÈØ´Àà´ÄÀ¨¨()A½¥¹ÐÑ¡”1$…Ð„Ñ•µÁ½É…Éä‘…Ñ…‰…Í”Á½ÁÕ±…Ñ•™É½´Ñ¡”•á¥ÍÑ¥¹œÁÉ¥Ù…Ñ”…¡”¸½µÁ…É”Ñ¥•È°`Ä°É…‘”°…¹Q½À€ÄÀ½É‘•ÈÝ¥Ñ Ñ¡”Ù…±¥‘…Ñ•±•…ä½ÕÑÁÕÑÌ¸MÑ½É”½¹±ä¹½¸µÁÉ¥Ù…Ñ”…É•…Ñ”…ÍÍ•ÉÑ¥½¹Ì¥¸¥Ðì‘¼¹½Ð½ÁäÑ¡”™Õ±°Ý…Ñ¡±¥ÍÐ½ÈÉ…Ü…¡”¥¹Ñ¼Ñ¡”ÁÕ‰±¥ŒÉ•Á½Í¥Ñ½Éä¸((´lt€¨©MÑ•À€Øè½µµ¥ÐÑ¡”‘…¥±äÁ¥Á•±¥¹”¨¨()‰…Í )¥Ð…‘ÍÉŒ½…ÍÍ°½Á¥Á•±¥¹”¹ÁäÍÉŒ½…ÍÍ°½±¤¹ÁäÑ•ÍÑÌ½™…­•Ì¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}Á¥Á•±¥¹”¹ÁäÑ•ÍÑÌ½Ñ•ÍÑ}±¤¹Áä)¥Ð½µµ¥Ð€µ´€‰™•…Ðè…‘¥‘•µÁ½Ñ•¹Ð‘…¥±äÍÉ••¹¥¹œÁ¥Á•±¥¹”ˆ)€((´´´((ŒŒA±…¸€Ä½µÁ±•Ñ¥½¸…Ñ”()IÕ¸…±°½µµ…¹‘Ì™É½´Ñ¡”É•Á½Í¥Ñ½ÉäÉ½½Ðè()‰…Í )ÁåÑ¡½¸€µ´ÉÕ™˜¡•¬ÍÉŒÑ•ÍÑÌ)ÁåÑ¡½¸€µ´ÁåÑ•ÍÐ€µ´€‰¹½Ð¥¹Ñ•É…Ñ¥½¸…¹¹½Ð¹•ÑÝ½É¬ˆ€µØ)ÁåÑ¡½¸€µ´ÁåÑ•ÍÐÑ•ÍÑÌ½¥¹Ñ•É…Ñ¥½¸½Ñ•ÍÑ}‘ˆ¹Áä€µØ€µ´¥¹Ñ•É…Ñ¥½¸)…ÍÍ°ÉÕ¸µ‘…¥±ä€´µ…Ìµ½˜€ÈÀÈØ´Àà´ÄÄ€´µ½™™±¥¹”)¥ÐÍÑ…ÑÕÌ€´µÍ¡½ÉÐ)€()½µÁ±•Ñ¥½¸É•ÅÕ¥É•Ì±¥¹ÐÍÕ•ÍÌ°…±°Õ¹¥Ð½É•É•ÍÍ¥½¸Ñ•ÍÑÌÁ…ÍÍ¥¹œ°‘…Ñ…‰…Í”¥¹Ñ•É…Ñ¥½¸Á…ÍÍ¥¹œ½¸Ñ¡”…ÁÁÉ½Ù•MÕÁ…‰…Í”‰É…¹ ½ÁÉ½©•Ð°‘•Ñ•Éµ¥¹¥ÍÑ¥Œ½™™±¥¹”½ÕÑÁÕÐ°…¹„±•…¸Ý½É­ÑÉ•”¸Q¡•¸É•ÅÕ•ÍÐ„½‘”É•Ù¥•Ü‰•™½É”ÍÑ…ÉÑ¥¹œA±…¸€È¸(