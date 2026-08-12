import { describe, expect, it } from "vitest";
import { assertSnapshot } from "../src/data";

const fixture = { schema_version:"1",as_of_date:"2026-08-11",generated_at:"",algorithm_version:"macd-v1",source:"腾讯",coverage:{},summary:{},top10:[],p1:[],p2:[],risk_watch:[],outcome_summary:[],disclaimer:"research" };

describe("public data boundary", () => {
  it("accepts the exact public root", () => expect(() => assertSnapshot(fixture)).not.toThrow());
  it("rejects private or unknown fields", () => expect(() => assertSnapshot({...fixture, watchlist:["600000"]})).toThrow(/watchlist/));
});
