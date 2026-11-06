import React from 'react';
import {windowContributions,entryNumbers} from './timelineRisk.js';
const num=value=>Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2});
const date=value=>value?value.slice(5).replace('-','/'):'待补';

export default function WindowContributions({window,entries,projects,rules,onSelect,onTotal,onHighlight,highlightedId,label='整段累计',compact=false}) {
  if(!window)return null;
  const contributions=windowContributions(window,entries,rules);
  const numbers=entryNumbers(entries);
  return <div className={`window-contributions rank-${window.rank} ${compact?'connected-formula':''}`} aria-label="核查时段工时合计来源">
    {onTotal?<button className="scope-total" onClick={onTotal} aria-label={`高亮整段累计${num(window.demand)}工日的全部来源`}><span>{label}</span><strong>{num(window.demand)}</strong> 工日</button>:<span className="scope-total">{label} <strong>{num(window.demand)}</strong> 工日</span>}
    <span className="sum-period">{window.start.slice(5).replace('-','/')}—{window.end.slice(5).replace('-','/')}</span>
    <span className="sum-symbol">＝</span>
    {contributions.map((entry,i)=>{
      const name=projects.find(p=>p.id===entry.project_id)?.name||'项目待补';
      const title=`${name} · ${entry.start||'日期待补'}—${entry.end||'日期待补'} · 申报${num(entry.amount)}${entry.unit}${entry.unit!=='工日'&&entry.days!=null?`，折合${num(entry.days)}工日`:''}`;
      const content=<><span className="claim-number" aria-label={`申报${numbers.get(entry.id)}`}>{numbers.get(entry.id)}</span><span className="source-copy"><span className="source-name">{name}</span><span className="source-dates">{date(entry.start)}—{date(entry.end)}</span></span><b>{entry.days==null?`${num(entry.amount)}${entry.unit}`:`${num(entry.days)}工日`}</b></>;
      return <React.Fragment key={entry.id}>{i>0&&<span className="sum-symbol">＋</span>}{onSelect?<button className={'source-chip '+(highlightedId===entry.id?'source-highlight':'')} data-entry-id={entry.id} title={title} onMouseEnter={()=>onHighlight?.(entry.id)} onMouseLeave={()=>onHighlight?.(null)} onFocus={()=>onHighlight?.(entry.id)} onBlur={()=>onHighlight?.(null)} onClick={()=>onSelect(entry.id)} aria-label={`查看合计来源：${name}`}>{content}</button>:<span className="source-chip" title={title}>{content}</span>}</React.Fragment>;
    })}
  </div>;
}
