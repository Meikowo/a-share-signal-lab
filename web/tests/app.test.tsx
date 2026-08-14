import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("renders independent branding, navigation and daily candidates", async () => {
    render(<App />);
    expect(await screen.findByText("今日技术面候选")).toBeVisible();
    expect(screen.getByText("ASSL")).toBeVisible();
    for (const label of ["今日信号", "历史记录", "策略回测", "方法说明"])
      expect(screen.getByRole("link", { name: new RegExp(label) })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /查看/ })).toHaveLength(5);
    expect(screen.queryByText(/ChatGPT|OpenAI/)).not.toBeInTheDocument();
  });

  it("renders matured forward outcome statistics", async () => {
    location.hash = "#/backtest";
    const withOutcomes = {
      ...snapshot,
      outcome_summary: [
        {
          bucket: "all",
          horizon_days: 5,
          sample_count: 32,
          win_rate: 0.625,
          avg_net_return: 0.0123,
          avg_excess_return: 0.0042,
          avg_mae: -0.031,
        },
        {
          bucket: "top10",
          horizon_days: 5,
          sample_count: 12,
          win_rate: 0.75,
          avg_net_return: 0.02,
          avg_excess_return: 0.009,
          avg_mae: -0.018,
        },
      ],
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

    await userEvent.click(screen.getByRole("button", { name: "Top10" }));
    expect(screen.getByText("75.0%")).toBeVisible();
    expect(screen.getByText("2.0%")).toBeVisible();
    expect(screen.getByText("-1.8%")).toBeVisible();
    expect(screen.getByText("12")).toBeVisible();
  });

  it("shows a selected historical list with per-stock matured outcomes", async () => {
    location.hash = "#/history";
    const historical = {
      ...snapshot,
      as_of_date: "2026-08-10",
      summary: { top10_count: 1, p1_count: 0, p2_count: 0, risk_count: 1 },
      top10: [{
        ...snapshot.top10[0],
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
    for (const tab of ["Top10", "P1", "P2", "风险观察"])
      expect(screen.getByRole("button", { name: tab })).toBeVisible();
    expect(screen.getByText("+2.4%")).toBeVisible();
    expect(screen.getByText("最大浮亏 -1.3%")).toBeVisible();
    expect(screen.getAllByText("观察中")).toHaveLength(3);

    await userEvent.click(screen.getByRole("button", { name: "风险观察" }));
    expect(screen.getByText("历史风险股")).toBeVisible();
    expect(screen.getByText("不纳入正向回测")).toBeVisible();
  });
});
