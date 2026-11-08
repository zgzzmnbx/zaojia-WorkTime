import React from 'react';
import { entryNumbers } from './timelineRisk.js';

const num = value => Number(value).toLocaleString('zh-CN', value > 0 && value < .01 ? {maximumSignificantDigits: 2} : {maximumFractionDigits: 2});

export default function ScheduleRiskList({items, result, projects, scope, onLocate, onEntry, onEvidence}) {
  const numbers = entryNumbers(result.entries);
  if (!items.length) return <div className="schedule-risk-empty" role="status">当前人员未检出工期预警或待核事项</div>;
  return <div className="table-scroll"><table className="table table-sm schedule-risk-table" aria-label="当前人员全部工期风险">
    <thead><tr><th>风险 / 依据</th><th>核查时段</th><th>涉及申报</th><th>操作</th></tr></thead>
    <tbody>{items.map(item => <tr key={item.id} data-risk-id={item.id} className={item.kind === 'window' && item.start === scope?.start && item.end === scope?.end ? 'selected-row' : ''}>
      <td>
        <div className="schedule-risk-heading">
          <span className={`badge badge-sm flow-risk rank-${item.kind === 'window' ? item.rank : item.level === 'warning' ? 2 : 'pending'}`}>{item.label}</span>
          <span>{item.category}</span>
        </div>
        <p className="schedule-risk-message">{item.kind === 'window'
          ? `合计 ${num(item.window.demand)} 工日 · ${item.comparison.boundary} ${num(item.comparison.threshold)} 工日 · 超出 ${num(item.comparison.excess)} 工日`
          : item.message}</p>
      </td>
      <td className="schedule-risk-period">{item.start && item.end ? <>{item.start}<br/>{item.end}</> : item.entryIds.length ? '日期待补' : '当前人员全期'}</td>
      <td><div className="schedule-risk-sources">{item.entryIds.length ? item.entryIds.map(id => {
        const entry = result.entries.find(entry => entry.id === id);
        return <button key={id} className="btn btn-ghost btn-xs" title={entry ? `${entry.start || '日期待补'} — ${entry.end || '日期待补'}` : id} onClick={() => { if (item.window) onLocate(item.window); onEntry(id); }}>
          <span className="entry-index">{numbers.get(id) || '—'}</span>{projects.find(project => project.id === entry?.project_id)?.name || '申报待核'}
        </button>;
      }) : <span className="muted">当前人员</span>}</div></td>
      <td><button className="btn btn-ghost btn-sm" onClick={() => item.kind === 'window' ? onLocate(item.window) : item.entryIds.length ? onEntry(item.entryIds[0]) : onEvidence()}>{item.kind === 'window' ? '定位时段' : '查看依据'}</button></td>
    </tr>)}</tbody>
  </table></div>;
}
