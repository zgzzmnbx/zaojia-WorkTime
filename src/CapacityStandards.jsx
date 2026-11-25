import React from 'react';
import {capacityStandards} from './timelineRisk.js';
import './capacity-standards.css';
const num=value=>Number(value).toLocaleString('zh-CN',value>0&&value<.01?{maximumSignificantDigits:2}:{maximumFractionDigits:2});

export default function CapacityStandards({window,rules={},showResult=true}) {
  const standard=capacityStandards(window,rules);
  if(!standard)return null;
  return <section className="capacity-standards" aria-label="本时段的三项比较标准">
    <div className="standards-heading"><strong>这段时间的参考量</strong><span>工日</span></div>
    <dl>{standard.rows.map(row=><div className="standard-row" key={row.id}>
      <dt>{row.label}<small>{row.basis}</small></dt><dd>{num(row.value)}<small>{row.exceeded?'申报已超过':'申报未超过'}</small></dd>
    </div>)}</dl>
    {standard.tolerance>0&&<p className="standard-note">各参考量已加 {num(standard.tolerance)} 工日容差。</p>}
    <div className="standard-bands" aria-label="本时段四级风险界线" title="按工作日参考、含加班上限和最高参考上限三条界线划分，均为模拟筛查">
      <span className="rank-0">低风险：≤ {num(standard.bands.green)} 工日</span>
      {standard.bands.yellow>standard.bands.green&&<span className="rank-1">中风险：＞ {num(standard.bands.green)} 且 ≤ {num(standard.bands.yellow)} 工日</span>}
      {standard.bands.red>standard.bands.yellow&&<span className="rank-2">高风险：＞ {num(standard.bands.yellow)} 且 ≤ {num(standard.bands.red)} 工日</span>}
      <span className="rank-3">极高风险：＞ {num(standard.bands.red)} 工日</span>
    </div>
    {showResult&&<p className={`standard-result rank-${window.rank}`} role="status" aria-label={standard.equation}>
      <small>{standard.comparison.exceeded?'申报 − 本次比较参考':'申报 ≤ 工作日参考'}</small>
      <strong>{standard.comparison.exceeded?`${num(window.demand)} − ${num(standard.comparison.threshold)} ＝ ${num(standard.comparison.excess)} 工日`:`${num(window.demand)} ≤ ${num(standard.comparison.threshold)} 工日`}</strong>
      {standard.comparison.exceeded&&<span>多出 {num(standard.comparison.excess)} 工日</span>}
    </p>}
    {(window.missing_calendar?.length>0||window.basis&&window.basis!=='人员投入期')&&<p className="standard-note">{window.missing_calendar?.length>0?'日历待补，参考量为暂估。':'投入日期待补，当前按项目实施期暂估。'}</p>}
  </section>;
}
