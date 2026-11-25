import {unitLabel} from './units.js';
import React from 'react';
import { capacityExplanation, capacityStandards,windowContributions } from './timelineRisk.js';
import CapacityStandards from './CapacityStandards.jsx';

const num=value=>value==null?'待补':Number(value).toLocaleString('zh-CN',value>0&&value<.01?{maximumSignificantDigits:2}:{maximumFractionDigits:2});

export default function RiskEvidence({risk,result,projects,onEdit}) {
  const entry=result.entries.find(entry=>entry.id===risk.entryIds[0]);
  const project=projects.find(project=>project.id===entry?.project_id);
  const window=risk.window;
  return <div className="detail-section first risk-evidence" key={risk.id}>
    <div className="schedule-risk-heading"><span className={`badge badge-sm flow-risk rank-${window?risk.rank:risk.level==='warning'?2:'pending'}`}>{risk.label}</span><strong>{risk.category}</strong></div>
    <p className="detail-meta">{risk.start&&risk.end?`${risk.start} — ${risk.end}`:risk.entryIds.length?'投入日期待补':'当前人员全期'}</p>
    {window?<>
      <p>{capacityStandards(window,result.rule_snapshot)?.sentence}</p>
      <CapacityStandards window={window} rules={result.rule_snapshot} showResult={false}/>
      <details className="detail-section"><summary>模拟加班怎么算</summary><p>{capacityExplanation(window,result.rule_snapshot)}</p></details>
      <div className="detail-section"><h4>涉及哪些完整申报</h4>{windowContributions(window,result.entries,result.rule_snapshot).map(e=><p key={e.id}><strong>{projects.find(p=>p.id===e.project_id)?.name}</strong><br/>{e.start} 至 {e.end}<br/>{num(e.amount)} {unitLabel(e.unit)}</p>)}</div>
      <p className="standard-note">请核对数量、日期及加班依据。期间交叉不能直接认定重复报工或推算审减量。</p>
    </>:<>
      {project&&<p className="detail-project">{project.name}</p>}
      <p>{risk.message}</p>
      {entry&&<dl><dt>本条申报</dt><dd>{num(entry.amount)} {unitLabel(entry.unit)}</dd>{risk.category==='实施期'&&<><dt>项目实施期</dt><dd>{project?.impl_start||'待补'}<br/>{project?.impl_end||'待补'}</dd><dt>实施期依据</dt><dd>{project?.impl_source||'待补'}</dd></>}</dl>}
      {entry&&<button className="btn btn-ghost btn-sm" onClick={()=>onEdit(entry)}>编辑申报</button>}
    </>}
    <details className="detail-section"><summary>规则与日历来源</summary><p>规则 v{result.rule_snapshot.rule_version} · 模拟</p>{result.calendar_sources.map(calendar=><p key={calendar.year}>{calendar.year}：{calendar.source}</p>)}</details>
  </div>;
}
