import React from 'react';
import { capacityExplanation, riskExplanation } from './timelineRisk.js';

const num=value=>Number(value).toLocaleString('zh-CN',value>0&&value<.01?{maximumSignificantDigits:2}:{maximumFractionDigits:2});

export default function RiskEvidence({risk,result,projects,onEdit}) {
  const entry=result.entries.find(entry=>entry.id===risk.entryIds[0]);
  const project=projects.find(project=>project.id===entry?.project_id);
  const window=risk.window;
  return <div className="detail-section first risk-evidence" key={risk.id}>
    <div className="schedule-risk-heading"><span className={`badge badge-sm flow-risk rank-${window?risk.rank:risk.level==='warning'?2:'pending'}`}>{risk.label}</span><strong>{risk.category}</strong></div>
    <p className="detail-meta">{risk.start&&risk.end?`${risk.start} — ${risk.end}`:risk.entryIds.length?'投入日期待补':'当前人员全期'}</p>
    {window?<>
      <p>{riskExplanation(window,result.rule_snapshot)}</p>
      <dl><dt>合计申报</dt><dd>{num(window.demand)} 工日</dd><dt>常规参考</dt><dd>{num(window.c0)} 工日</dd><dt>加班后参考</dt><dd>{num(window.c1)} 工日</dd><dt>高负荷参考</dt><dd>{num(window.c2)} 工日</dd><dt>超出{risk.comparison.boundary}</dt><dd>{num(risk.comparison.excess)} 工日</dd></dl>
      <details className="detail-section"><summary>容量计算口径</summary><p>{capacityExplanation(window,result.rule_snapshot)}</p></details>
    </>:<>
      {project&&<p className="detail-project">{project.name}</p>}
      <p>{risk.message}</p>
      {entry&&<dl><dt>本条申报</dt><dd>{num(entry.amount)} {entry.unit}</dd>{risk.category==='实施期'&&<><dt>项目实施期</dt><dd>{project?.impl_start||'待补'}<br/>{project?.impl_end||'待补'}</dd><dt>实施期依据</dt><dd>{project?.impl_source||'待补'}</dd></>}</dl>}
      {entry&&<button className="btn btn-ghost btn-sm" onClick={()=>onEdit(entry)}>编辑申报</button>}
    </>}
    <details className="detail-section"><summary>规则与日历来源</summary><p>规则 v{result.rule_snapshot.rule_version} · 模拟</p>{result.calendar_sources.map(calendar=><p key={calendar.year}>{calendar.year}：{calendar.source}</p>)}</details>
  </div>;
}
