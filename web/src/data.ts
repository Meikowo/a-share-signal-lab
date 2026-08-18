export type Candidate = {
  rank: number | null; symbol: string; name: string; bucket: string | null;
  grade: string; signal_type: string; signal_date: string | null; dif: number;
  dea: number; macd_hist: number; gap: number; convergence_speed: number | null;
  x1: number | null; x1_change_pct: number | null; projected_days: number | null;
  ma20: number | null; ma30: number | null; ma60: number | null;
  close_vs_ma20: number | null; close_vs_ma30: number | null; close_vs_ma60: number | null;
  volume_ratio_5_20: number | null; bottom_divergence: boolean; top_divergence: boolean;
  reason: string; confirm_price: number | null; invalidation_price: number | null;
  risk: string | null; outcomes: CandidateOutcome[];
};

export type CandidateOutcome = {
  horizon_days: number; entry_date: string; exit_date: string;
  net_return: number; mae: number;
};

export type Snapshot = {
  schema_version: "1"; as_of_date: string; generated_at: string; algorithm_version: string;
  source: string; coverage: { universe_count: number; covered_count: number; missing_count: number; coverage_ratio: number; publishable: boolean };
  summary: { top10_count: number; p1_count: number; p2_count: number; risk_count: number };
  top10: Candidate[]; p1: Candidate[]; p2: Candidate[]; risk_watch: Candidate[];
  outcome_summary: OutcomeSummary[]; disclaimer: string;
};

export type OutcomeSummary = {
  bucket?: "all" | "top10" | "p1" | "p2";
  horizon_days: number; sample_count: number; win_rate: number;
  avg_net_return: number; avg_excess_return: number; avg_mae?: number;
};

export type Manifest = { schema_version:"1"; algorithm_version:string; latest_date:string; history_dates:string[]; generated_at:string; file_sha256:Record<string,string> };

const ROOT_KEYS = ["schema_version","as_of_date","generated_at","algorithm_version","source","coverage","summary","top10","p1","p2","risk_watch","outcome_summary","disclaimer"];

export function assertSnapshot(value: unknown): asserts value is Snapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("无效的快照格式");
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) if (!ROOT_KEYS.includes(key)) throw new Error(`未知字段: ${key}`);
  for (const key of ROOT_KEYS) if (!(key in record)) throw new Error(`缺少字段: ${key}`);
  if (record.schema_version !== "1" || typeof record.as_of_date !== "string") throw new Error("快照版本无效");
}

function safeBase(base: string) {
  if (/^(?:[a-z]+:)?\/\//i.test(base) || base.includes("..")) throw new Error("数据路径必须为同源路径");
  return base.replace(/\/$/, "");
}

function freshDataUrl(base: string, path: string) {
  return `${safeBase(base)}/${path}?v=${Date.now()}`;
}

const DEFAULT_DATA = `${import.meta.env.BASE_URL}data${import.meta.env.DEV ? "/fixture" : ""}`;

export async function loadManifest(base = DEFAULT_DATA) : Promise<Manifest> {
  const response = await fetch(freshDataUrl(base, "manifest.json"), { cache: "no-store" });
  if (!response.ok || !response.headers.get("content-type")?.includes("json")) throw new Error("无法读取历史索引");
  return response.json();
}

export async function loadSnapshot(day?: string, base = DEFAULT_DATA) : Promise<Snapshot> {
  const path = day ? `history/${encodeURIComponent(day)}.json` : "latest.json";
  const response = await fetch(freshDataUrl(base, path), { cache: "no-store" });
  if (!response.ok || !response.headers.get("content-type")?.includes("json")) throw new Error("无法读取信号快照");
  const value: unknown = await response.json(); assertSnapshot(value); return value;
}
