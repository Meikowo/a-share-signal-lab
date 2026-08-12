# ASSL Public Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy the approved public ASSL dashboard, history, backtest, and methodology experience using only privacy-checked static JSON.

**Architecture:** A Vite/React static application loads Plan 2's `public-data` bundle through a narrow data client. The UI uses an independent ASSL identity with neutral gray-white surfaces, generous spacing, restrained color, a desktop sidebar, and a mobile single-column layout; it does not connect to Supabase at runtime.

**Tech Stack:** Node.js 22+, TypeScript 5.8+, React 19, Vite 7, Vitest, Testing Library, Playwright, plain CSS, SVG charts, GitHub Pages.

## Global Constraints

- Plan 2 completion gate must pass before this plan starts.
- Runtime network requests are limited to same-origin files under `data/`; no Supabase client is allowed in `web/`.
- Do not use OpenAI Sans, OpenAI/ChatGPT names, logos, icons, or proprietary assets.
- Visual direction: neutral gray-white, generous whitespace, weak borders, restrained radii, natural reading hierarchy, minimal accent color.
- Chinese A-share convention: red denotes positive/up, green denotes negative/down; color is never the only carrier of meaning.
- Complete watchlist, internal fundamental labels, raw bars, and private signal rows must not appear in the built site.
- Every view shows data cutoff, algorithm version, source, coverage/missing state, and research-only disclaimer.
- The site must remain usable at 360 CSS pixels wide and with keyboard-only navigation.

## File Map

- `web/package.json` — frontend dependencies and scripts.
- `web/vite.config.ts` — GitHub Pages base path and build settings.
- `web/src/data/types.ts` — public snapshot TypeScript contract.
- `web/src/data/client.ts` — same-origin manifest/history loading and validation.
- `web/src/styles/tokens.css` — independent ASSL design tokens.
- `web/src/styles/global.css` — resets, typography, responsive shell.
- `web/src/components/AppShell.tsx` — sidebar, mobile header, status footer.
- `web/src/components/SignalSummary.tsx` — readable daily narrative.
- `web/src/components/CandidateList.tsx` — ranked candidates and filters.
- `web/src/components/CandidateDetail.tsx` — metric and outcome detail drawer.
- `web/src/components/PerformanceChart.tsx` — accessible SVG performance view.
- `web/src/pages/TodayPage.tsx` — latest daily overview.
- `web/src/pages/HistoryPage.tsx` — immutable date browsing.
- `web/src/pages/BacktestPage.tsx` — versioned outcome summaries.
- `web/src/pages/MethodPage.tsx` — method, cost, limitations, disclaimer.
- `web/src/App.tsx` — hash routing and top-level error boundary.
- `web/public/data/fixture/` — synthetic public fixtures only.
- `web/tests/` — component and data-client tests.
- `web/e2e/` — Playwright desktop/mobile/accessibility flows.
- `.github/workflows/ci.yml` — frontend checks added.
- `.github/workflows/daily.yml` — Pages build/deploy added after private-data job.

---

### Task 1: Scaffold the Static Web App and Typed Data Client

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/data/types.ts`
- Create: `web/src/data/client.ts`
- Create: `web/public/data/fixture/latest.json`
- Create: `web/public/data/fixture/manifest.json`
- Create: `web/tests/data-client.test.ts`

**Interfaces:**
- Consumes: Plan 2 `manifest.json`, `latest.json`, and `history/*.json`
- Produces: `loadManifest(baseUrl?: string) -> Promise<PublicManifest>`
- Produces: `loadSnapshot(date?: string, baseUrl?: string) -> Promise<PublicSnapshot>`
- Produces: `assertPublicSnapshot(value: unknown) -> asserts value is PublicSnapshot`

- [ ] **Step 1: Write failing data-client tests**

```ts
it("loads only same-origin JSON under data", async () => {
  const snapshot = await loadSnapshot(undefined, "/data/fixture");
  expect(snapshot.as_of_date).toBe("2026-08-11");
  expect(snapshot.top10).toHaveLength(3);
});

it("rejects private and unknown fields", () => {
  expect(() => assertPublicSnapshot({...fixture, watchlist: ["600000"]}))
    .toThrow(/unknown field: watchlist/);
});
```

- [ ] **Step 2: Verify failure**

Run: `cd web && npm test -- --run tests/data-client.test.ts`  
Expected: FAIL before the web project exists.

- [ ] **Step 3: Add exact scripts and dependencies**

`web/package.json` scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest",
    "test:run": "vitest run",
    "e2e": "playwright test",
    "lint": "eslint ."
  }
}
```

Use React 19, Vite 7, TypeScript 5.8+, Vitest, Testing Library, ESLint, and Playwright. Commit `package-lock.json`; do not use a CDN.

- [ ] **Step 4: Implement runtime validation and URL restrictions**

Mirror the JSON Schema fields exactly in TypeScript. Define `PublicManifest` as `{ schema_version: "1"; algorithm_version: string; latest_date: string; history_dates: string[]; generated_at: string; file_sha256: Record<string, string> }`; define `PublicSnapshot` and nested candidate/outcome types with the exact Task 3 fields from Plan 2. `client.ts` must reject absolute URLs, protocol-relative URLs, `..` path segments, non-JSON responses, and unknown fields. All fetches resolve beneath `${import.meta.env.BASE_URL}data/` in production.

Vite config uses:

```ts
export default defineConfig({
  base: process.env.GITHUB_ACTIONS ? "/a-share-signal-lab/" : "/",
  plugins: [react()],
});
```

- [ ] **Step 5: Run tests and build**

Run: `cd web && npm ci && npm run test:run && npm run build`  
Expected: tests pass; `web/dist/index.html` exists; no request URL references Supabase.

- [ ] **Step 6: Commit web foundation**

```bash
git add web
git commit -m "feat(web): bootstrap typed static dashboard"
```

---

### Task 2: Implement the Approved ASSL Application Shell

**Files:**
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/global.css`
- Create: `web/src/components/AppShell.tsx`
- Create: `web/src/components/StatusBadge.tsx`
- Create: `web/src/App.tsx`
- Create: `web/tests/app-shell.test.tsx`

**Interfaces:**
- Produces: `<AppShell activeRoute status>{children}</AppShell>`
- Produces routes: `#/today`, `#/history`, `#/backtest`, `#/method`

- [ ] **Step 1: Write shell/navigation tests**

```tsx
it("renders independent ASSL branding and all primary routes", () => {
  render(<App />);
  expect(screen.getByText("ASSL")).toBeVisible();
  for (const label of ["今日信号", "历史记录", "策略回测", "方法说明"])
    expect(screen.getByRole("link", {name: label})).toBeVisible();
  expect(screen.queryByText(/ChatGPT|OpenAI/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Verify failure**

Run: `cd web && npm run test:run -- tests/app-shell.test.tsx`  
Expected: FAIL because the shell is absent.

- [ ] **Step 3: Implement design tokens and layout**

Use these token values as the approved starting point:

```css
:root {
  --assl-bg: #ffffff;
  --assl-sidebar: #f9f9f9;
  --assl-hover: #ececec;
  --assl-text: #181818;
  --assl-muted: #737373;
  --assl-line: #e8e8e8;
  --assl-soft: #f7f7f7;
  --assl-up: #b83b34;
  --assl-down: #0f7b55;
  --assl-radius-sm: 9px;
  --assl-radius-lg: 15px;
  --assl-content: 1120px;
}
```

Desktop uses a 240px sticky sidebar and centered content. Below 900px the sidebar becomes a compact header/menu and content padding becomes 18px. Use system UI fonts only.

- [ ] **Step 4: Implement hash navigation and route focus behavior**

Each nav item is a real link. On route change, focus the page heading. Active state uses background and text, not color alone. Add skip-to-content. Status badge shows completed, partial, failed-last-run, or stale-last-success states.

- [ ] **Step 5: Run tests and visual smoke**

Run: `cd web && npm run test:run -- tests/app-shell.test.tsx && npm run build`  
Expected: pass. Open local dev server at desktop and 390px widths and confirm no horizontal page scroll.

- [ ] **Step 6: Commit shell**

```bash
git add web/src web/tests/app-shell.test.tsx
git commit -m "feat(web): add approved ASSL visual shell"
```

---

### Task 3: Build the Today Dashboard and Candidate Detail

**Files:**
- Create: `web/src/components/SignalSummary.tsx`
- Create: `web/src/components/MetricStrip.tsx`
- Create: `web/src/components/CandidateList.tsx`
- Create: `web/src/components/CandidateDetail.tsx`
- Create: `web/src/components/RiskWatch.tsx`
- Create: `web/src/pages/TodayPage.tsx`
- Create: `web/tests/today-page.test.tsx`

**Interfaces:**
- Consumes: `PublicSnapshot`
- Produces: filter values `all | confirmed | p1 | p2`
- Produces: candidate detail dialog keyed by symbol

- [ ] **Step 1: Write readable-summary and candidate tests**

```tsx
it("shows cutoff, coverage, research summary, candidates, and disclaimer", async () => {
  render(<TodayPage snapshot={fixture} />);
  expect(screen.getByText(/2026-08-11/)).toBeVisible();
  expect(screen.getByText(/覆盖率 99.4%/)).toBeVisible();
  expect(screen.getByRole("heading", {name: "今日信号摘要"})).toBeVisible();
  expect(screen.getAllByTestId("candidate-row")).toHaveLength(3);
  expect(screen.getByText(/不构成确定买入建议/)).toBeVisible();
});

it("opens a keyboard-accessible detail dialog", async () => {
  render(<TodayPage snapshot={fixture} />);
  await user.click(screen.getByRole("button", {name: /查看 示例科技/}));
  expect(screen.getByRole("dialog", {name: /示例科技/})).toHaveFocus();
  expect(screen.getByText("DIF")).toBeVisible();
  expect(screen.getByText("失效位")).toBeVisible();
});
```

- [ ] **Step 2: Verify failure**

Run: `cd web && npm run test:run -- tests/today-page.test.tsx`  
Expected: FAIL because page components are absent.

- [ ] **Step 3: Implement summary and metrics without invented prose**

The narrative uses structured snapshot counts and fixed templates; it must not call an LLM or invent reasons. Show StrongS/S, P1, P2, matured 5-day sample count, 5-day win rate only if at least 30 matured samples, and average CSI 300 excess.

- [ ] **Step 4: Implement candidate reading list and detail dialog**

Desktop row columns are rank, stock, grade, reason, key levels, and open-detail action. Mobile rows become stacked cards. Detail includes all approved fields: dates, DIF/DEA/hist/gap/convergence, X1 and percentage, projected days, MA20/30/60, close-relative values, volume, divergences, grade, reason, confirmation, invalidation, risk, and matured outcomes.

Use both text and badges for grade/risk. A recent top-divergence row belongs only to `RiskWatch`, never Top 10.

- [ ] **Step 5: Run component tests**

Run: `cd web && npm run test:run -- tests/today-page.test.tsx`  
Expected: pass, including missing-X1, partial coverage, insufficient-sample, and empty-risk fixtures.

- [ ] **Step 6: Commit Today page**

```bash
git add web/src/components web/src/pages/TodayPage.tsx web/tests/today-page.test.tsx
git commit -m "feat(web): render daily candidates and details"
```

---

### Task 4: Build History, Backtest, and Method Pages

**Files:**
- Create: `web/src/components/PerformanceChart.tsx`
- Create: `web/src/components/OutcomeTable.tsx`
- Create: `web/src/pages/HistoryPage.tsx`
- Create: `web/src/pages/BacktestPage.tsx`
- Create: `web/src/pages/MethodPage.tsx`
- Create: `web/tests/history-page.test.tsx`
- Create: `web/tests/backtest-page.test.tsx`
- Create: `web/tests/method-page.test.tsx`

**Interfaces:**
- Consumes: `PublicManifest`, dated `PublicSnapshot`, methodology JSON
- Produces: accessible SVG chart with text table fallback

- [ ] **Step 1: Write history immutability/date-loading tests**

```tsx
it("loads a selected immutable history date", async () => {
  render(<HistoryPage manifest={manifest} loadSnapshot={loader} />);
  await user.selectOptions(screen.getByLabelText("交易日"), "2026-08-10");
  expect(loader).toHaveBeenCalledWith("2026-08-10");
  expect(await screen.findByText(/算法 legacy-macd-v1/)).toBeVisible();
});
```

- [ ] **Step 2: Write backtest separation and sample-warning tests**

Assert fixed 1/5/10/20-day rows are separate from signal-exit rows, algorithm versions are filterable, sample count is visible, and `<30` samples displays `样本不足` instead of a headline win rate.

- [ ] **Step 3: Verify failure**

Run: `cd web && npm run test:run -- tests/history-page.test.tsx tests/backtest-page.test.tsx tests/method-page.test.tsx`  
Expected: FAIL because pages are absent.

- [ ] **Step 4: Implement pages and accessible chart**

`PerformanceChart` renders SVG lines with labeled axes and includes a visually available table showing date, ASSL value, CSI 300 value, and excess. Do not imply a tradable portfolio when insufficient results exist; title it “候选等权观察表现”.

Method page displays exact MACD/MA parameters, A/B/C definitions, grades, T+1 entry, 10 bps per leg, CSI 300 benchmark, data source, missing-data policy, algorithm versioning, known limitations, and disclaimer.

- [ ] **Step 5: Run page tests**

Run: `cd web && npm run test:run -- tests/history-page.test.tsx tests/backtest-page.test.tsx tests/method-page.test.tsx`  
Expected: pass.

- [ ] **Step 6: Commit research pages**

```bash
git add web/src/components/PerformanceChart.tsx web/src/components/OutcomeTable.tsx web/src/pages web/tests
git commit -m "feat(web): add history backtest and method views"
```

---

### Task 5: Add Loading, Failure, Stale, and Empty States

**Files:**
- Create: `web/src/components/ViewState.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/pages/TodayPage.tsx`
- Create: `web/tests/view-states.test.tsx`

**Interfaces:**
- Produces states: `loading`, `empty`, `partial`, `stale`, `last_run_failed`, `fatal`

- [ ] **Step 1: Write state tests**

```tsx
it("keeps last successful data visible when the latest run failed", () => {
  render(<App initialData={staleFixture} />);
  expect(screen.getByText(/本期计算失败/)).toBeVisible();
  expect(screen.getByText(/当前展示上次成功结果：2026-08-11/)).toBeVisible();
  expect(screen.getAllByTestId("candidate-row")).not.toHaveLength(0);
});
```

Also test a network/JSON failure does not render an empty Top 10 as if successful.

- [ ] **Step 2: Verify failure**

Run: `cd web && npm run test:run -- tests/view-states.test.tsx`  
Expected: FAIL because view states are absent.

- [ ] **Step 3: Implement explicit states**

Loading uses text and lightweight skeletons. Partial shows covered/missing counts. Stale and failed states use a persistent notice above the date. Fatal schema/load errors show retry and methodology links. Empty is permitted only for a successful run whose snapshot explicitly contains zero candidates.

- [ ] **Step 4: Run tests and commit**

Run: `cd web && npm run test:run -- tests/view-states.test.tsx`  
Expected: pass.

```bash
git add web/src web/tests/view-states.test.tsx
git commit -m "feat(web): add honest data and failure states"
```

---

### Task 6: Add Responsive, Accessibility, and Privacy E2E Tests

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/e2e/dashboard.spec.ts`
- Create: `web/e2e/mobile.spec.ts`
- Create: `web/e2e/privacy.spec.ts`
- Modify: `web/package.json`

**Interfaces:**
- E2E base URL: local Vite preview with synthetic public fixtures

- [ ] **Step 1: Write desktop and keyboard flows**

Test page load, route navigation, date selection, candidate dialog open/close, focus return, table fallback, and disclaimer visibility. Capture screenshots at 1440×1000 for review.

- [ ] **Step 2: Write 390px and 360px mobile flows**

Assert no horizontal document overflow, candidate cards remain readable, navigation is reachable, and detail content scrolls inside the viewport. Capture 390×844 screenshots.

- [ ] **Step 3: Write browser-level privacy tests**

Inspect all responses and built resources. Fail on `supabase.co`, `postgresql://`, `sb_secret_`, `fundamental_priority`, `theme_tags`, `watchlist_members`, or any non-public fixture symbol cluster.

- [ ] **Step 4: Run and fix until all E2E checks pass**

Run: `cd web && npm run build && npx playwright test`  
Expected: all desktop, mobile, keyboard, and privacy tests pass; screenshots match the approved neutral layout.

- [ ] **Step 5: Commit E2E coverage**

```bash
git add web/playwright.config.ts web/e2e web/package.json web/package-lock.json
git commit -m "test(web): verify responsive accessible public site"
```

---

### Task 7: Deploy the Validated Site to GitHub Pages

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/daily.yml`
- Create: `tests/test_pages_workflow.py`
- Modify: `docs/operations.md`
- Create: `README.md`

**Interfaces:**
- Consumes: privacy-checked `public-data/`
- Produces: GitHub Pages artifact containing `web/dist/` with `data/` copied inside

- [ ] **Step 1: Write Pages workflow contract tests**

Assert `daily.yml` grants only `contents: read`, `pages: write`, and `id-token: write`; the build job copies public data after privacy scan; deploy depends on build; concurrency does not cancel an in-progress daily data write.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_pages_workflow.py -v`  
Expected: FAIL until workflow is updated.

- [ ] **Step 3: Extend CI for the frontend**

CI runs `npm ci`, frontend lint/tests/build, and Playwright smoke with fixture data. Python privacy scan runs against `web/dist` after the build.

- [ ] **Step 4: Extend the daily workflow for Pages**

After Plan 2 export and privacy scan:

1. install Node.js 22 and run `npm ci`;
2. remove `web/public/data/fixture/` in the runner, then copy `public-data/*` to `web/public/data/` without staging either change in git;
3. run frontend tests and build;
4. scan `web/dist` again;
5. configure Pages and upload `web/dist` using official GitHub Pages actions;
6. deploy only when all previous steps succeed.

The repository itself never commits generated production data.

- [ ] **Step 5: Create public README and operational notes**

README states purpose, public/private boundary, data source, update timing, methodology link, local development with synthetic fixtures, and disclaimer. It must not describe the full private watchlist or expose setup secrets.

- [ ] **Step 6: Verify locally and deploy manually first**

Run:

```bash
python -m pytest tests/test_pages_workflow.py tests/test_workflows.py -v
cd web && npm ci && npm run test:run && npm run build && npx playwright test
python -m assl.publish.privacy web/dist
```

Expected: all pass. Then use `workflow_dispatch` on an already completed date, inspect the Pages artifact, confirm the visible date/coverage/candidates/history, and only then enable the schedule.

- [ ] **Step 7: Commit Pages deployment**

```bash
git add .github/workflows tests/test_pages_workflow.py docs/operations.md README.md
git commit -m "ci: deploy ASSL to GitHub Pages"
```

---

## Plan 3 Completion Gate

```bash
python -m ruff check src scripts tests
python -m pytest -m "not integration and not network" -v
cd web && npm ci && npm run lint && npm run test:run && npm run build && npx playwright test
python -m assl.publish.privacy web/dist
git status --short
```

Completion additionally requires a successful manual GitHub Pages deployment, desktop and mobile visual review against the approved mockup, confirmation that browser network requests are same-origin only, public inspection showing no watchlist/private fields/credentials, correct last-success failure behavior, and a clean worktree.
