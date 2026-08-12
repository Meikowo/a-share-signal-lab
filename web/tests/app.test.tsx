import { render, screen } from "@testing-library/react";
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
  afterEach(() => vi.unstubAllGlobals());

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
});
