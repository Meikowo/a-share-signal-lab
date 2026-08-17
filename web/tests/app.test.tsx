import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import snapshot from "../public/data/fixture/latest.json";
import manifest from "../public/data/fixture/manifest.json";

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
      }],
    };
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(url.includes("manifest") ? manifest : withOutcomes),
    })));

    render(<App />);

    expect(await screen.findByText("62.5%")).toBeVisible();
    expect(screen.getByText("0.4%")).toBeVisible();
    expect(screen.getByText("32")).toBeVisible();
  });

  it("keeps experimental strategies isolated in the strategy lab", async () => {
    location.hash = "#/lab";

    render(<App />);

    expect(await screen.findByRole("heading", { name: "策略实验室" })).toBeVisible();
    expect(screen.getByText(/生产基线/)).toBeVisible();
    expect(screen.getByText("市场环境与参与度")).toBeVisible();
    expect(screen.getByText("行业与个股相对强度")).toBeVisible();
    expect(screen.getByText("上升趋势回撤修复")).toBeVisible();
    expect(screen.getByText("基本面证据叠加")).toBeVisible();
    expect(screen.getByText(/不会自动混入今日 Top 10/)).toBeVisible();
  });
});
