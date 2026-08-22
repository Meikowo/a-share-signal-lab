import { useEffect, useMemo, useState } from "react";
import { Candidate, CandidateOutcome, Manifest, MarketRegimeEntry, MarketRegimeReport, Snapshot, loadManifest, loadMarketRegime, loadSnapshot } from "./data";

type Route = "today" | "history" | "backtest" | "lab" | "method";
const NAV: [Route,string,string][] = [["today","今日信号","⌁"],["history","历史记录","◷"],["backtest","策略回测","↗"],["lab","策略实验室","◎"],["method","方法说明","◇"]];

function currentRoute(): Route { const value=location.hash.replace("#/",""); return NAV.some(([r])=>r===value) ? value as Route : "today"; }

export default function App() {
  const [route,setRoute]=useState<Route>(currentRoute());
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
  const [manifest,setManifest]=useState<Manifest|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{ const handler=()=>setRoute(currentRoute()); addEventListener("hashchange",handler); return()=>removeEventListener("hashchange",handler);},[]);
  useEffect(()=>{ Promise.all([loadSnapshot(),loadManifest()]).then(([s,m])=>{setSnapshot(s);setManifest(m)}).catch(e=>setError(String(e.message||e)));},[]);
  return <div className="app-shell">
    <a className="skip" href="#main">跳到主要内容</a>
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">A</span><span><b>ASSL</b><small>A股信号实验室</small></span></div>
      <nav aria-label="主要导航">{NAV.map(([key,label,icon])=><a key={key} href={`#/${key}`} className={route===key?"active":""}><i>{icon}</i>{label}</a>)}</nav>
      <div className="side-foot"><span className="live-dot"/> 数据每日更新<small>仅作研究参考</small></div>
    </aside>
    <main id="main">
      {error ? <ErrorState message={error}/> : !snapshot ? <Loading/> : route==="today" ? <Today snapshot={snapshot}/> : route==="history" ? <History snapshot={snapshot} manifest={manifest}/> : route==="backtest" ? <Backtest snapshot={snapshot}/> : route==="lab" ? <StrategyLab snapshot={snapshot}/> : <Method snapshot={snapshot}/>}
    </main>
  </div>
}

function PageHeader({eyebrow,title,children}:{eyebrow:string,title:string,children?:React.ReactNode}) { return <header className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1 tabIndex={-1}>{title}</h1></div>{children}</header> }

function Today({snapshot}:{snapshot:Snapshot}) {
  const [filter,setFilter]=useState("all"); const [selected,setSelected]=useState<Candidate|null>(null);
  const candidates=useMemo(()=>filter==="confirmed"?snapshot.top10.filter(x=>x.signal_type==="confirmed_trend"):filter==="p1"?snapshot.p1:filter==="p2"?snapshot.p2:snapshot.top10,[snapshot,filter]);
  return <div className="content"><PageHeader eyebrow="DAILY SIGNALS" title="今日技术面候选"><div className="date-pill"><span/>截至 {snapshot.as_of_date} 收盘</div></PageHeader>
    <section className="metric-grid"><Metric value={String(snapshot.summary.top10_count)} label="今日 Top 10" note="研究优先级最高"/><Metric value={String(snapshot.top10.filter(x=>["强S","S"].includes(x.grade)).length)} label="强共振信号" note="底背离 + 金叉" accent/><Metric value={String(snapshot.summary.p1_count)} label="P1 临界金叉" note="预计 1.5 日内"/><Metric value={String(snapshot.summary.risk_count)} label="风险观察" note="近期顶背离" risk/></section>
    <div className="section-head"><div><span className="eyebrow">CANDIDATE POOL</span><h2>候选研究清单</h2></div><div className="filters">{[["all","全部"],["confirmed","已确认"],["p1","P1"],["p2","P2"]].map(([v,l])=><button key={v} className={filter===v?"selected":""} onClick={()=>setFilter(v)}>{l}</button>)}</div></div>
    <div className="candidate-table"><div className="table-head"><span>排名 / 股票</span><span>信号与等级</span><span>关键指标</span><span>确认 / 失效</span><span/></div>{candidates.length?candidates.map((c,i)=><CandidateRow key={c.symbol} candidate={c} rank={c.rank??i+1} onOpen={()=>setSelected(c)}/>):<div className="empty">当前分组暂无候选</div>}</div>
    {snapshot.p1.length+snapshot.p2.length>0&&<section className="watch-section"><h2>金叉酝酿观察</h2><div className="mini-grid">{[...snapshot.p1,...snapshot.p2].slice(0,4).map(c=><button className="mini-card" onClick={()=>setSelected(c)} key={c.symbol}><span className="grade">{c.grade}</span><b>{c.name}</b><small>{c.symbol} · {c.bucket?.toUpperCase()}</small><em>X1 {fmt(c.x1)}</em></button>)}</div></section>}
    {snapshot.risk_watch.length>0&&<section className="risk-section"><div><span className="risk-icon">!</span><div><b>风险观察</b><p>近期出现顶背离，不进入正向 Top 10。</p></div></div><div>{snapshot.risk_watch.map(c=><button onClick={()=>setSelected(c)} key={c.symbol}>{c.name}<small>{c.risk}</small></button>)}</div></section>}
    <footer className="disclaimer">{snapshot.disclaimer}<br/><small>模型信号不保证未来表现，请结合公司基本面、估值与自身风险承受能力独立判断。</small></footer>
    {selected&&<Detail candidate={selected} onClose={()=>setSelected(null)}/>}</div>
}

function Metric({value,label,note,accent,risk}:{value:string,label:string,note:string,accent?:boolean,risk?:boolean}) { return <article className={`metric ${accent?"accent":""} ${risk?"risk":""}`}><strong>{value}</strong><span>{label}</span><small>{note}</small></article> }
function CandidateRow({candidate:c,rank,onOpen}:{candidate:Candidate,rank:number,onOpen:()=>void}) { return <button className="candidate-row" onClick={onOpen} aria-label={`查看 ${c.name}`}><span className="stock"><i>{rank}</i><b>{c.name}<small>{c.symbol}</small></b></span><span><em className={`badge grade-${c.grade}`}>{c.grade}</em><small>{signalName(c)}</small></span><span className="metrics"><b>DIF {fmt(c.dif)}</b><small>柱 {fmt(c.macd_hist)} · 量比 {fmt(c.volume_ratio_5_20)}</small></span><span className="levels"><b>{fmt(c.confirm_price)}</b><small>失效 {fmt(c.invalidation_price)}</small></span><span className="arrow">→</span></button> }

function Detail({candidate:c,onClose}:{candidate:Candidate,onClose:()=>void}) { useEffect(()=>{ const h=(e:KeyboardEvent)=>e.key==="Escape"&&onClose();addEventListener("keydown",h);return()=>removeEventListener("keydown",h)},[onClose]); return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section role="dialog" aria-modal="true" aria-label={`${c.name} 信号详情`} className="modal" tabIndex={-1}><button className="close" onClick={onClose}>×</button><span className="eyebrow">SIGNAL DETAIL</span><h2>{c.name}<small>{c.symbol}</small></h2><div className="modal-summary"><em className={`badge grade-${c.grade}`}>{c.grade}</em><p>{c.reason}</p></div><div className="detail-grid"><DetailItem label="DIF" value={fmt(c.dif)}/><DetailItem label="DEA" value={fmt(c.dea)}/><DetailItem label="MACD 柱" value={fmt(c.macd_hist)}/><DetailItem label="收敛缺口 g" value={fmt(c.gap)}/><DetailItem label="X1 临界价" value={fmt(c.x1)}/><DetailItem label="预计天数" value={c.projected_days==null?"—":`${c.projected_days.toFixed(1)} 日`}/><DetailItem label="MA20 / 30 / 60" value={`${fmt(c.ma20)} / ${fmt(c.ma30)} / ${fmt(c.ma60)}`}/><DetailItem label="5日/20日量能" value={fmt(c.volume_ratio_5_20)}/></div><div className="level-grid"><div><span>关键确认位</span><strong>{fmt(c.confirm_price)}</strong></div><div><span>失效位</span><strong>{fmt(c.invalidation_price)}</strong></div></div>{c.risk&&<div className="risk-note">风险：{c.risk}</div>}<button className="primary" onClick={onClose}>完成</button></section></div> }
function DetailItem({label,value}:{label:string,value:string}) { return <div><span>{label}</span><strong>{value}</strong></div> }

function History({snapshot,manifest}:{snapshot:Snapshot,manifest:Manifest|null}) {
  type HistoryBucket = "top10" | "p1" | "p2" | "risk_watch";
  const buckets: [HistoryBucket,string][]=[["top10","Top10"],["p1","P1"],["p2","P2"],["risk_watch","风险观察"]];
  const dates=manifest?.history_dates??[snapshot.as_of_date]; const [shown,setShown]=useState(snapshot); const [bucket,setBucket]=useState<HistoryBucket>("top10"); const [loading,setLoading]=useState(false); const [error,setError]=useState("");
  const choose=async(day:string)=>{setLoading(true);setError("");try{setShown(day===snapshot.as_of_date?snapshot:await loadSnapshot(day));setBucket("top10")}catch(e){setError(String((e as Error).message||e))}finally{setLoading(false)}};
  const candidates=shown[bucket];
  return <div className="content"><PageHeader eyebrow="IMMUTABLE HISTORY" title="历史信号记录"/><section className="plain-card history-card"><label>选择交易日<select value={shown.as_of_date} disabled={loading} onChange={e=>void choose(e.target.value)}>{dates.map(d=><option key={d}>{d}</option>)}</select></label>{error&&<p className="risk-note">{error}</p>}<h2>{shown.as_of_date} · {shown.algorithm_version}</h2><p>信号快照保持不变；已经成熟的前瞻收益会持续追加到历史观察记录。</p><div className="metric-grid"><Metric value={String(shown.summary.top10_count)} label="Top 10" note="当日研究优先级"/><Metric value={String(shown.summary.p1_count)} label="P1" note="临界金叉"/><Metric value={String(shown.summary.p2_count)} label="P2" note="金叉酝酿"/><Metric value={String(shown.summary.risk_count)} label="风险观察" note="不进入正向榜单" risk/></div><div className="history-layout"><div className="timeline">{dates.slice().reverse().map((d,i)=><button key={d} onClick={()=>void choose(d)} className={shown.as_of_date===d?"selected":""}><span/><b>{d}</b><small>{i===0?"最新成功快照":"历史快照"}</small></button>)}</div><section className="history-results" aria-label={`${shown.as_of_date} 候选列表`}><div className="section-head"><div><span className="eyebrow">DAILY LEDGER</span><h2>当日候选与后续表现</h2></div><div className="filters history-filters">{buckets.map(([value,label])=><button key={value} className={bucket===value?"selected":""} onClick={()=>setBucket(value)}>{label}</button>)}</div></div><div className={`history-table ${loading?"loading":""}`}><div className="history-head"><span>股票 / 信号</span>{[1,5,10,20].map(h=><span key={h}>T+{h}</span>)}</div>{candidates.length?candidates.map((candidate,index)=><HistoryCandidateRow key={candidate.symbol} candidate={candidate} rank={candidate.rank??index+1} riskOnly={bucket==="risk_watch"}/>):<div className="empty">该分组当日没有候选</div>}</div></section></div></section></div>
}
function HistoryCandidateRow({candidate:c,rank,riskOnly}:{candidate:Candidate,rank:number,riskOnly:boolean}) { const outcomes=new Map(c.outcomes.map(row=>[row.horizon_days,row])); return <article className="history-row"><div className="history-stock"><span className="stock"><i>{rank}</i><b>{c.name}<small>{c.symbol}</small></b></span><span><em className={`badge grade-${c.grade}`}>{c.grade}</em><small>{signalName(c)}</small></span></div>{riskOnly?<div className="history-risk-status">不纳入正向回测<small>{c.risk??"风险观察仅保留历史记录"}</small></div>:[1,5,10,20].map(h=><OutcomeCell key={h} horizon={h} outcome={outcomes.get(h)}/>)}</article> }
function OutcomeCell({horizon,outcome}:{horizon:number,outcome?:CandidateOutcome}) { if(!outcome)return <div className="outcome-cell pending"><small>T+{horizon}</small><b>观察中</b></div>; const value=outcome.net_return; return <div className="outcome-cell"><small>T+{horizon} · {outcome.exit_date}</small><b className={value>0?"return-up":value<0?"return-down":""}>{signedPct(value)}</b><span>区间最大回撤 {pct(Math.min(outcome.mae,0))}</span></div> }
function Backtest({snapshot}:{snapshot:Snapshot}) {
  const [bucket,setBucket]=useState<"all"|"top10"|"p1"|"p2">("all"); const visible=snapshot.outcome_summary.filter(row=>(row.bucket??"all")===bucket); const byHorizon=new Map(visible.map(row=>[row.horizon_days,row])); const mature=visible.reduce((sum,row)=>sum+row.sample_count,0);
  return <div className="content"><PageHeader eyebrow="FORWARD OUTCOMES" title="候选效果追踪"/><section className="plain-card"><div className="section-head"><div><h2>前瞻观察，不是回填胜率</h2><p>信号次日开盘进入观察，固定 1 / 5 / 10 / 20 个交易日收盘评估；绝对收益已扣除买卖各 10bp 成本。</p></div><div className="filters">{[["all","全部"],["top10","Top10"],["p1","P1"],["p2","P2"]].map(([value,label])=><button key={value} className={bucket===value?"selected":""} onClick={()=>setBucket(value as typeof bucket)}>{label}</button>)}</div></div><div className="outcome-table"><div><b>观察窗口</b><b>成熟样本</b><b>胜率</b><b>平均绝对收益</b><b>平均最大回撤</b></div>{[1,5,10,20].map(h=>{const row=byHorizon.get(h);return <div key={h}><span>{h} 日</span><span>{row?.sample_count??0}</span><span className={!row||row.sample_count<30?"muted":""}>{row?pct(row.win_rate):"样本不足"}</span><span>{row?pct(row.avg_net_return):"—"}</span><span>{row?.avg_mae==null?"—":pct(Math.min(row.avg_mae,0))}</span></div>})}</div>{mature<30&&<div className="empty-chart"><span>⌁</span><b>等待前瞻样本成熟</b><p>至少 30 个成熟样本后，胜率才具有初步观察价值；当前分组已形成 {mature} 个“窗口样本”。</p></div>}</section></div>
}
function StrategyLab({snapshot}:{snapshot:Snapshot}) {
  const [report,setReport]=useState<MarketRegimeReport|null>(null);
  const [selectedDate,setSelectedDate]=useState("");
  const [experimentError,setExperimentError]=useState("");
  useEffect(()=>{loadMarketRegime().then(value=>{setReport(value);setSelectedDate(value.latest_date??value.history.at(-1)?.as_of_date??"")}).catch(error=>setExperimentError(String(error.message||error)))},[]);
  const entry=report?.history.find(row=>row.as_of_date===selectedDate)??report?.history.at(-1);
  const experiments = [
    ["02", "行业与个股相对强度", "比较行业对宽基、个股对行业的 20 / 60 日强弱", "准备实验"],
    ["03", "上升趋势回撤修复", "中期趋势未破坏、缩量回撤后的重新确认", "准备实验"],
    ["04", "基本面证据叠加", "以有时间戳的研究证据调整优先级，不做简单好坏二分", "研究设计"],
  ];
  return <div className="content"><PageHeader eyebrow="STRATEGY LAB" title="策略实验室"><div className="date-pill"><span/>独立影子运行</div></PageHeader>
    <section className="lab-baseline"><div><span className="eyebrow">PRODUCTION BASELINE</span><h2>MACD 仍是生产基线</h2><p>{snapshot.algorithm_version} 继续负责今日候选。实验策略先独立记录、独立回测，不会自动混入今日 Top 10。</p></div><span className="status-chip live">生产中</span></section>
    <section className="market-lab"><div className="market-lab-head"><div><span className="eyebrow">EXPERIMENT 01 · SHADOW RUN</span><h2>市场环境与参与度 V1</h2><p>用沪深300趋势与自选池聚合宽度、参与度和压力判断信号可信度；完整自选池不会公开。</p></div>{report&&report.history.length>0&&<label>观察日期<select aria-label="市场环境观察日期" value={entry?.as_of_date??""} onChange={event=>setSelectedDate(event.target.value)}>{report.history.slice().reverse().map(row=><option key={row.as_of_date}>{row.as_of_date}</option>)}</select></label>}</div>
      {experimentError?<div className="experiment-empty">{experimentError}</div>:!report?<div className="experiment-empty">正在读取实验结果…</div>:report.status==="unavailable"?<div className="experiment-empty">市场环境实验暂时不可用，MACD 主榜仍正常更新。</div>:!entry?<div className="experiment-empty">历史样本尚未生成，下一次数据导出后自动补充。</div>:<MarketRegimePanel entry={entry} report={report}/>}
    </section>
    <div className="lab-heading"><div><span className="eyebrow">RESEARCH QUEUE</span><h2>后续策略研究队列</h2></div><p>先证明增量价值，再讨论合并权重。</p></div>
    <section className="experiment-grid">{experiments.map(([number,title,description,status])=><article key={number}><div><i>{number}</i><span className="status-chip">{status}</span></div><h2>{title}</h2><p>{description}</p><footer>观察 T+1 / T+5 / T+10 / T+20、最大回撤与样本覆盖</footer></article>)}</section>
    <section className="lab-rule"><b>晋级规则</b><p>新策略至少经过历史重构和前瞻影子样本，在不同市场环境下相对 MACD 基线仍有稳定增益，才进入正式综合排名。</p></section>
  </div>
}
function MarketRegimePanel({entry,report}:{entry:MarketRegimeEntry,report:MarketRegimeReport}) {
  const stateLabel=entry.state==="risk_on"?"风险偏好":entry.state==="neutral"?"中性震荡":"风险规避";
  const hasOutcomes=report.outcome_comparison.some(row=>row.baseline.sample_count>0||row.adjusted.sample_count>0);
  const components=[
    ["指数趋势",entry.components.benchmark_trend,`沪深300相对MA20 ${signedPct(entry.components.benchmark_trend.close_vs_ma20)}`],
    ["市场宽度",entry.components.breadth,`MA20之上 ${pct(entry.components.breadth.above_ma20_ratio)}`],
    ["参与活跃",entry.components.participation,`上涨比例 ${pct(entry.components.participation.advancing_ratio)}`],
    ["下跌压力",entry.components.stress,`大跌比例 ${pct(entry.components.stress.large_decline_ratio)}`],
  ] as const;
  return <><div className={`regime-summary ${entry.state}`}><div className="regime-score"><strong>{entry.score.toFixed(1)}</strong><span>市场温度 / 100</span></div><div><span className="status-chip">{stateLabel}</span><h3>{entry.policy}</h3><p>原始 {entry.baseline_top10_count} · 调整后 {entry.adjusted_top10.length}　｜　聚合覆盖 {entry.covered_count} / {entry.universe_count}　｜　{sampleTypeName(entry.sample_type)}</p></div></div>
    <div className="regime-components">{components.map(([name,component,note])=><article key={name}><div><b>{name}</b><strong>{component.score.toFixed(1)}<small> / {component.max_score}</small></strong></div><span>{note}</span></article>)}</div>
    <div className="lab-two-column"><section><div className="section-head"><div><span className="eyebrow">ADJUSTMENT LEDGER</span><h2>当日信号处理</h2></div></div><div className="decision-list">{entry.decisions.map(row=><article key={`${row.original_bucket}-${row.symbol}`}><div><b>{row.name}<small>{row.symbol} · {row.grade}</small></b><em className={`decision-${row.action}`}>{actionName(row.action)}</em></div><p>{row.reason}</p></article>)}</div></section><section><div className="section-head"><div><span className="eyebrow">BASELINE VS FILTERED</span><h2>历史效果对照</h2></div></div><div className="regime-outcomes"><div><b>样本</b><b>窗口</b><b>样本：原始 / 调整</b><b>平均收益：原始 / 调整</b><b>最大回撤：原始 / 调整</b></div>{report.outcome_comparison.map(row=><div key={`${row.sample_type}-${row.horizon_days}`}><span>{sampleTypeName(row.sample_type)}</span><span>T+{row.horizon_days}</span><span>{row.baseline.sample_count} / {row.adjusted.sample_count}</span><span>{optionalPair(row.baseline.avg_net_return,row.adjusted.avg_net_return)}</span><span>{optionalPair(row.baseline.avg_mae,row.adjusted.avg_mae)}</span></div>)}</div>{!hasOutcomes&&<div className="experiment-empty compact">等待成熟的前瞻样本</div>}<p className="experiment-note">历史重构可能包含自选池存续偏差；真实前瞻影子样本单独统计。{report.methodology.industry_diffusion}</p></section></div></>
}
function actionName(action:string){return action==="keep"?"保留":action==="downgrade"?"降级":action==="monitor"?"跟踪":"观察"}
function sampleTypeName(value:MarketRegimeEntry["sample_type"]){return value==="forward_shadow"?"真实前瞻":"历史重构"}
function optionalPair(left:number|null,right:number|null){return `${left==null?"—":signedPct(left)} / ${right==null?"—":signedPct(right)}`}
function Method({snapshot}:{snapshot:Snapshot}) { return <div className="content"><PageHeader eyebrow="METHODOLOGY" title="方法与边界"/><section className="method-grid"><article><i>01</i><h2>三条信号通道</h2><p>确认金叉与趋势启动、因果底背离修复、P1/P2 条件性预测金叉。顶背离只作风险扣分。</p></article><article><i>02</i><h2>固定参数</h2><p>MACD 12 / 26 / 9；均线 MA20 / MA30 / MA60；前复权日线，明确收盘截止日。</p></article><article><i>03</i><h2>基本面叠加</h2><p>量化负责择时，已有主线与基本面研究负责排序优先级。内部标签不会出现在公开网站。</p></article><article><i>04</i><h2>效果验证</h2><p>T+1 开盘、双边各 10bp、沪深300基准，固定周期与信号退出分别统计。</p></article></section><section className="plain-card method-note"><h2>数据与限制</h2><p>数据源：{snapshot.source}。当前算法：{snapshot.algorithm_version}。覆盖不足 97% 时不会发布新候选。技术信号可能失效，市场制度、停牌、涨跌停和流动性都会影响实际可交易性。</p></section></div> }
function Loading(){return <div className="state"><span className="spinner"/><h2>正在读取最新信号</h2><p>请稍候</p></div>}
function ErrorState({message}:{message:string}){return <div className="state"><b>!</b><h2>暂时无法读取公开数据</h2><p>{message}</p><a href="#/method">查看方法说明</a></div>}
function fmt(v:number|null){return v==null||!Number.isFinite(v)?"—":v.toFixed(3)}
function pct(v:number){return Number.isFinite(v)?`${(v*100).toFixed(1)}%`:"—"}
function signedPct(v:number){return Number.isFinite(v)?`${v>0?"+":""}${(v*100).toFixed(1)}%`:"—"}
function signalName(c:Candidate){return c.signal_type==="confirmed_trend"?"已确认金叉":c.signal_type==="bottom_divergence"?"底背离修复":c.bucket==="p1"?"P1 临界金叉":c.bucket==="p2"?"P2 金叉酝酿":"技术面候选"}
