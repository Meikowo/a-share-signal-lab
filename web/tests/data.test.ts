import { afterEach, describe, expect, it, vi } from "vitest";

import manifest from "../public/data/fixture/manifest.json";
import snapshot from "../public/data/fixture/latest.json";
import { assertSnapshot, loadManifest, loadSnapshot } from "../src/data";

const fixture = { schema_version:"1",as_of_date:"2026-08-11",generated_at:"",algorithm_version:"macd-v1",source:"腾讯",coverage:{},summary:{},top10:[],p1:[],p2:[],risk_watch:[],outcome_summary:[],disclaimer:"research" };

describe("public data boundary", () => {
  it("accepts the exact public root", () => expect(() => assertSnapshot(fixture)).not.toThrow());
  it("rejects private or unknown fields", () => expect(() => assertSnapshot({...fixture, watchlist:["600000"]})).toThrow(/watchlist/));
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
    });
  vi.stubGlobal("fetch", fetchMock);

  await loadManifest("/data");
  await loadSnapshot(undefined, "/data");

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
});
