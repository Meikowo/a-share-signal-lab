import { afterEach, describe, expect, it, vi } from "vitest";

import manifest from "../public/data/fixture/manifest.json";
import snapshot from "../public/data/fixture/latest.json";
import { assertSnapshot, loadManifest, loadMarketRegime, loadSnapshot } from "../src/data";

const fixture = { schema_version:"1",as_of_date:"2026-08-11",generated_at:"",algorithm_version:"macd-v1",source:"腾讯",coverage:{},summary:{},top10:[],p1:[],p2:[],risk_watch:[],outcome_summary:[],disclaimer:"research" };

describe("public data boundary", () => {
  it("accepts the exact public root", () => expect(() => assertSnapshot(fixture)).not.toThrow());
  it("rejects private or unknown fields", () => expect(() => assertSnapshot({...fixture, watchlist:["600000"]})).toThrow(/watchlist/));
});

it("rejects a malformed market-regime entry before the UI renders it", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve({
      schema_version: "1",
      history: [{ as_of_date: "2026-08-21", score: 42, state: "risk_off" }],
      outcome_comparison: [],
      methodology: { industry_diffusion: "pending" },
    }),
  }));

  await expect(loadMarketRegime("/data")).rejects.toThrow(/格式/);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("bypasses browser and CDN caches for public data", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(manifest),
    })
    .mockResolvedValueOnce({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(snapshot),
    })
    .mockResolvedValueOnce({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({
        schema_version: "1",
        experiment_version: "market-regime-v1",
        algorithm_version: "macd-v1.1",
        latest_date: null,
        status: "available",
        history: [],
        unavailable: [],
        outcome_comparison: [],
        methodology: { industry_diffusion: "pending" },
      }),
    });
  vi.stubGlobal("fetch", fetchMock);

  await loadManifest("/data");
  await loadSnapshot(undefined, "/data");
  await loadMarketRegime("/data");

  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    expect.stringMatching(/^\/data\/manifest\.json\?v=\d+$/),
    { cache: "no-store" },
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    expect.stringMatching(/^\/data\/latest\.json\?v=\d+$/),
    { cache: "no-store" },
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    expect.stringMatching(/^\/data\/experiments\/market-regime\.json\?v=\d+$/),
    { cache: "no-store" },
  );
});
