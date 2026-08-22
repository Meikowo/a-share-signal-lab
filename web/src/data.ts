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

export type MarketRegimeComponent = Record<string, number> & { score:number; max_score:number };
export type MarketRegimeCandidate = { symbol:string; name:string; grade:string; signal_type:string };
export type MarketRegimeDecision = MarketRegimeCandidate & {
  original_bucket:"top10"|"p1"|"p2"; action:"keep"|"downgrade"|"monitor"|"observation"; reason:string;
};
export type MarketRegimeEntry = {
  as_of_date:string; score:number; state:"risk_on"|"neutral"|"risk_off";
  sample_type:"historical_reconstruction"|"forward_shadow";
  universe_count:number; covered_count:number; baseline_top10_count:number;
  components:{ benchmark_trend:MarketRegimeComponent; breadth:MarketRegimeComponent; participation:MarketRegimeComponent; stress:MarketRegimeComponent };
  adjusted_top10:MarketRegimeCandidate[]; decisions:MarketRegimeDecision[]; policy:string;
};
export type RegimeOutcome = { sample_count:number; avg_net_return:number|null; avg_mae:number|null };
export type MarketRegimeReport = {
  schema_version:"2"; experiment_version:string; algorithm_version:string; latest_date:string|null;
  status:"available"|"unavailable";
  history:MarketRegimeEntry[];
  unavailable:{ as_of_date:string; sample_type:MarketRegimeEntry["sample_type"]; reason:string }[];
  outcome_comparison:{ sample_type:MarketRegimeEntry["sample_type"]; horizon_days:number; baseline:RegimeOutcome; adjusted:RegimeOutcome }[];
  methodology:{ industry_diffusion:string; [key:string]:unknown };
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

export async function loadMarketRegime(base = DEFAULT_DATA): Promise<MarketRegimeReport> {
  const response = await fetch(freshDataUrl(base, "experiments/market-regime.json"), { cache: "no-store" });
  if (!response.ok || !response.headers.get("content-type")?.includes("json")) throw new Error("无法读取市场环境实验");
  const value: unknown = await response.json();
  assertMarketRegimeReport(value);
  return value as MarketRegimeReport;
}

function assertMarketRegimeReport(value: unknown): asserts value is MarketRegimeReport {
  const record = objectRecord(value);
  if (record.schema_version !== "2" || typeof record.experiment_version !== "string" || typeof record.algorithm_version !== "string") invalidRegime();
  if (record.status !== "available" && record.status !== "unavailable") invalidRegime();
  if (record.latest_date !== null && typeof record.latest_date !== "string") invalidRegime();
  if (!Array.isArray(record.history) || !Array.isArray(record.unavailable) || !Array.isArray(record.outcome_comparison)) invalidRegime();
  record.history.forEach(assertMarketRegimeEntry);
  record.unavailable.forEach(item => {
    const row = objectRecord(item);
    if (typeof row.as_of_date !== "string" || !isSampleType(row.sample_type) || typeof row.reason !== "string") invalidRegime();
  });
  record.outcome_comparison.forEach(item => {
    const row = objectRecord(item);
    if (!isSampleType(row.sample_type) || !isFiniteNumber(row.horizon_days) || ![1,5,10,20].includes(row.horizon_days)) invalidRegime();
    assertRegimeOutcome(row.baseline);
    assertRegimeOutcome(row.adjusted);
  });
  const methodology = objectRecord(record.methodology);
  if (typeof methodology.industry_diffusion !== "string") invalidRegime();
}

function assertMarketRegimeEntry(value: unknown) {
  const row = objectRecord(value);
  if (typeof row.as_of_date !== "string" || !isSampleType(row.sample_type) || !isFiniteNumber(row.score)) invalidRegime();
  if (!isFiniteNumber(row.universe_count) || !isFiniteNumber(row.covered_count) || !isFiniteNumber(row.baseline_top10_count)) invalidRegime();
  if (!['risk_on','neutral','risk_off'].includes(String(row.state)) || typeof row.policy !== "string") invalidRegime();
  const components = objectRecord(row.components);
  assertRegimeComponent(components.benchmark_trend, "close_vs_ma20");
  assertRegimeComponent(components.breadth, "above_ma20_ratio");
  assertRegimeComponent(components.participation, "advancing_ratio");
  const participation = objectRecord(components.participation);
  for (const metric of ["total_market_amount","market_turnover_ratio_5_20","market_turnover_percentile_120","market_turnover_score","market_turnover_max_score","market_turnover_stress_capped"])
    if (!isFiniteNumber(participation[metric])) invalidRegime();
  assertRegimeComponent(components.stress, "large_decline_ratio");
  if (!Array.isArray(row.adjusted_top10) || !Array.isArray(row.decisions)) invalidRegime();
  row.adjusted_top10.forEach(assertRegimeCandidate);
  row.decisions.forEach(item => {
    assertRegimeCandidate(item);
    const decision = objectRecord(item);
    if (!['top10','p1','p2'].includes(String(decision.original_bucket)) || !['keep','downgrade','monitor','observation'].includes(String(decision.action)) || typeof decision.reason !== "string") invalidRegime();
  });
}

function assertRegimeComponent(value: unknown, requiredMetric: string) {
  const component = objectRecord(value);
  if (!isFiniteNumber(component.score) || !isFiniteNumber(component.max_score) || !isFiniteNumber(component[requiredMetric])) invalidRegime();
}

function assertRegimeCandidate(value: unknown) {
  const candidate = objectRecord(value);
  for (const key of ["symbol","name","grade","signal_type"]) if (typeof candidate[key] !== "string") invalidRegime();
}

function assertRegimeOutcome(value: unknown) {
  const row = objectRecord(value);
  if (!isFiniteNumber(row.sample_count) || row.sample_count < 0 || !Number.isInteger(row.sample_count) || !isOptionalFiniteNumber(row.avg_net_return) || !isOptionalFiniteNumber(row.avg_mae)) invalidRegime();
}

function objectRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalidRegime();
  return value as Record<string, unknown>;
}

function isSampleType(value: unknown): value is MarketRegimeEntry["sample_type"] { return value === "historical_reconstruction" || value === "forward_shadow"; }
function isFiniteNumber(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function isOptionalFiniteNumber(value: unknown) { return value === null || isFiniteNumber(value); }
function invalidRegime(): never { throw new Error("市场环境实验格式无效"); }
