import {unitLabel} from './units.js';
import React from 'react';

export function participatingClaim(entry) {
  return !['withdrawn', 'returned'].includes(entry.status) && entry.duplicate !== 'duplicate';
}

export function ClaimAppend({groups, checked, onChange}) {
  return <section className="duplicate-box claim-append" aria-label="追加申报">
    {groups.map(({key, label, entries, batchCount}) => <div key={key}>
      <strong>{label}</strong>
      {entries.length > 0 && <div className="claim-history-scroll">
        <table className="table table-sm">
          <caption>本项目已有申报（{entries.length} 条）</caption>
          <thead><tr><th>投入开始</th><th>投入结束</th><th>申报数量</th><th>累计状态</th></tr></thead>
          <tbody>{entries.map(entry => <tr key={entry.id}>
            <td>{entry.start || '待补'}</td><td>{entry.end || '待补'}</td>
            <td>{entry.amount ?? '待补'} {unitLabel(entry.unit)}</td>
            <td>{participatingClaim(entry) ? '参与累计' : '不参与累计'}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      {batchCount > 1 && <p>本次录入 {batchCount} 条申报。</p>}
    </div>)}
    <label className="checkline">
      <input className="checkbox checkbox-sm" type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)}/>
      已核对，确认追加并参与累计
    </label>
  </section>;
}
