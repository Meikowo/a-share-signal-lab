import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import snapshot from "../public/data/fixture/latest.json";
import manifest from "../public/data/fixture/manifest.json";

const marketRegime = {
  schema_version: "2",
  experiment_version: "market-regime-v1.1",
  algorithm_version: "macd-v1.1",
  latest_date: "2026-08-11",
  status: "available",
  history: [{
    as_of_date: "2026-08-11", score: 42, state: "risk_off",
    sample_type: "historical_reconstruction",
    universe_count: 839, covered_count: 819, baseline_top10_count: 2,
    adjusted_top10: [{ symbol: "600001", name: "强信号股", grade: "强S", signal_type: "confirmed_trend" }],
    decisions: [
      { symbol: "600001", name: "强信号股", grade: "强S", signal_type: "confirmed_trend", original_bucket: "top10", action: "keep", reason: "强共振确认信号保留" },
      { symbol: "600002", name: "预测信号股", grade: "A", signal_type: "predictive_cross", original_bucket: "top10", action: "observation", reason: "风险规避期仅作观察" },
    ],
    components: {
      benchmark_trend: { score: 8, max_score: 30, close_vs_ma20: -0.03, close_vs_ma60: -0.08, ma20_slope_5d: -0.01, ma60_slope_5d: -0.005, realized_vol_20: 0.26 },
      breadth: { score: 12, max_score: 30, above_ma20_ratio: 0.3, above_ma60_ratio: 0.5 },
      participation: { score: 10, max_score: 25, advancing_ratio: 0.3, active_volume_ratio: 0.5, median_volume_ratio_20: 0.8, total_market_amount: 1880000000000, market_turnover_ratio_5_20: 1.08, market_turnover_percentile_120: 0.72, market_turnover_score: 7.1, market_turnover_max_score: 10, market_turnover_stress_capped: 0 },
      stress: { score: 12, max_score: 15, large_decline_ratio: 0.02, realized_vol_20: 0.26 },
    },
    policy: "暂停预测金叉晋级，仅保留强共振确认或底背离修复信号",
  }],
  outcome_comparison: [{
    sample_type: "historical_reconstruction",
    horizon_days: 5,
    baseline: { sample_count: 32, avg_net_return: -0.02, avg_mae: -0.08 },
    adjusted: { sample_count: 16, avg_net_return: 0.01, avg_mae: -0.04 },
  }],
  unavailable: [],
  methodology: { industry_diffusion: "待稳定行业分类数据后加入，不计入V1评分" },
};

describe("ASSL dashboard", () => {
  beforeEach(() => {
    location.hash = "#/today";
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(url.includes("manifest") ? manifest : snapshot),
    })));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders independent branding, navigation and daily candidates", async () => {
    render(<App />);
    expect(await screen.findByText("今日技术面候选")).toBeVisible();
    expect(screen.getByText("ASSL")).toBeVisible();
    for (const label of ["今日信号", "历史记录", "策略回测", "策略实验室", "方法说明"])
      expect(screen.getByRole("link", { name: new RegExp(label) })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /查看/ })).toHaveLength(5);
    expect(screen.queryByText(/ChatGPT|OpenAI/)).not.toBeInTheDocument();
  });

  it("keeps the daily metrics while omitting the dark summary hero", async () => {
    render(<App />);

    expect(await screen.findByText("今日 Top 10")).toBeVisible();
    expect(screen.queryByText("今日信号摘要")).not.toBeInTheDocument();
    expect(screen.queryByText("数据覆盖率")).not.toBeInTheDocument();
  });

  it("shows the configured 97 percent publication threshold", async () => {
    location.hash = "#/method";
    render(<App />);

    expect(await screen.findByText(/覆盖不足 97% 时不会发布新候选/)).toBeVisible();
  });

  it("renders matured forward outcome statistics", async () => {
    location.hash = "#/backtest";
    const withOutcomes = {
      ...snapshot,
      outcome_summary: [{
        horizon_days: 5,
        sample_count: 32,
        win_rate: 0.625,
        avg_net_return: 0.0123,
        avg_excess_return: 0.0042,
        avg_mae: -0.031,
      }],
    };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(url.includes("manifest") ? manifest : withOutcomes),
    })));

    render(<App />);

    expect(await screen.findByText("62.5%")).toBeVisible();
    expect(screen.getByText("1.2%")).toBeVisible();
    expect(screen.getByText("-3.1%")).toBeVisible();
    expect(screen.getByText("32")).toBeVisible();
  });

  it("keeps experimental strategies isolated in the strategy lab", async () => {
    location.hash = "#/lab";
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(url.includes("market-regime") ? marketRegime : url.includes("manifest") ? manifest : snapshot),
    })));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "策略实验室" })).toBeVisible();
    expect(screen.getByText(/生产基线/)).toBeVisible();
    expect(screen.getByText("市场环境与参与度 V1.1")).toBeVisible();
    expect(screen.getByText("风险规避")).toBeVisible();
    expect(screen.getByText("42.0")).toBeVisible();
    expect(screen.getByText(/两市成交额 1.88万亿/)).toBeVisible();
    expect(screen.getByText("暂停预测金叉晋级，仅保留强共振确认或底背离修复信号")).toBeVisible();
    expect(screen.getByText("强共振确认信号保留")).toBeVisible();
    expect(screen.getByText(/原始 2 · 调整后 1/)).toBeVisible();
    expect(screen.getAllByText("历史重构").length).toBeGreaterThan(0);
    expect(screen.getByText(/自选池存续偏差/)).toBeVisible();
    expect(screen.getByText("-2.0% / +1.0%")).toBeVisible();
    expect(screen.getByText("行业与个股相对强度")).toBeVisible();
    expect(screen.getByText("上升趋势回撤修复")).toBeVisible();
    expect(screen.getByText("基本面证据叠加")).toBeVisible();
    expect(screen.getByText(/不会自动混入今日 Top 10/)).toBeVisible();
  });

  it("shows a selected historical list with per-stock matured outcomes", async () => {
    location.hash = "#/history";
    const historical = {
      ...snapshot,
      as_of_date: "2026-08-10",
      summary: { top10_count: 1, p1_count: 0, p2_count: 0, risk_count: 1 },
      top10: [{
        ...snapshot.top10[0],
        symbol: "600000",
        name: "历史样本股",
        outcomes: [{
          horizon_days: 1,
          entry_date: "2026-08-11",
          exit_date: "2026-08-11",
          net_return: 0.024,
          mae: -0.013,
        }],
      }],
      p1: [],
      p2: [],
      risk_watch: [{ ...snapshot.risk_watch[0], name: "历史风险股" }],
    };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(
        url.includes("manifest") ? manifest : url.includes("history/") ? historical : snapshot
      ),
    })));

    render(<App />);
    await userEvent.selectOptions(await screen.findByLabelText("选择交易日"), "2026-08-10");

    expect(await screen.findByText("历史样本股")).toBeVisible();
    expect(screen.getByText("600000")).toBeVisible();
    expect(screen.getByText("+2.4%")).toBeVisible();
    expect(screen.getByText("区间最大回撤 -1.3%")).toBeVisible();
    expect(screen.getAllByText("观察中")).toHaveLength(3);

    await userEvent.click(screen.getByRole("button", { name: "风险观察" }));
    expect(screen.getByText("历史风险股")).toBeVisible();
    expect(screen.getByText("不纳入正向回测")).toBeVisible();
  });
});
