import React, { useEffect, useState } from 'react';
import { calendarDay, calendarRange } from './workCalendar.js';
import './calendar.css';

export default function CalendarManager({ Modal, state, actor, setActor, onSave, onClose, onManual, request }) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [start, setStart] = useState(now.getFullYear() + '-01-01');
  const [end, setEnd] = useState(now.getFullYear() + '-12-31');
  const [pack, setPack] = useState(null);
  const [selected, setSelected] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sourceUrl, setSourceUrl] = useState(state.calendar_update?.url || '');
  const [syncMessage, setSyncMessage] = useState('');
  const [automatic, setAutomatic] = useState(state.calendar_update?.automatic === true);
  const [syncStatus, setSyncStatus] = useState(null);
  const current = state.calendars.find(item => item.year === year);
  const summary = calendarRange(start, end, state.calendars);
  const monthStart = new Date(Date.UTC(year, month - 1, 1));
  const offset = (monthStart.getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, month, 0)).getUTCDate();

  function preview(value, selectChanges = false) {
    setPack(value);
    setSelected(value.calendars.filter(c => (value.fetched_from && automatic) || changeStatus(c) === '新增' || (selectChanges && changeStatus(c) === '有变化')).map(c => c.year));
  }
  function changeStatus(calendar) {
    const old = state.calendars.find(c => c.year === calendar.year);
    if (!old) return '新增';
    const dates = values => [...values].sort().join(',');
    return dates(old.holidays) === dates(calendar.holidays) && dates(old.makeup_days) === dates(calendar.makeup_days) && old.source === calendar.source ? '一致' : '有变化';
  }
  function dateChanges(calendar) {
    const old = state.calendars.find(c => c.year === calendar.year);
    if (!old) return [];
    const changes = [];
    for (const [key, label] of [['holidays', '放假'], ['makeup_days', '补班']]) {
      const added = calendar[key].filter(day => !old[key].includes(day));
      const removed = old[key].filter(day => !calendar[key].includes(day));
      if (added.length) changes.push(label + '新增 ' + added.join('、'));
      if (removed.length) changes.push(label + '取消 ' + removed.join('、'));
    }
    if (old.source !== calendar.source) changes.push('来源有更新');
    return changes;
  }
  useEffect(() => {
    let live = true;
    request('/calendar-bundle').then(value => { if (live) preview(value); }).catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, []);
  useEffect(() => {
    let live = true;
    const check = () => request('/calendar-update-status').then(value => { if (live) setSyncStatus(value); }).catch(() => {});
    check();
    const timer = setInterval(check, 15000);
    return () => { live = false; clearInterval(timer); };
  }, []);

  async function syncCalendar() {
    setBusy(true);
    setError('');
    setSyncMessage('');
    setPack(null);
    setSelected([]);
    try {
      const value = await request('/calendar-sync', { url: sourceUrl.trim() });
      preview(value, true);
      setSyncMessage('已连接内网服务，请核对下方年度变化后保存。');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function applyPackage(event) {
    event.preventDefault();
    if (automatic && !sourceUrl.trim()) { setError('启用自动同步前请填写内网日历服务地址'); return; }
    if (!selected.length && !sourceUrl.trim()) return;
    setBusy(true);
    setError('');
    try {
      const calendars = [...state.calendars.filter(c => !selected.includes(c.year)), ...(pack?.calendars || []).filter(c => selected.includes(c.year))].sort((a, b) => a.year - b.year);
      const calendar_update = sourceUrl.trim() ? { url: sourceUrl.trim(), checked_at: pack?.fetched_at || state.calendar_update?.checked_at, automatic } : state.calendar_update;
      await onSave({ ...state, calendars, ...(calendar_update ? { calendar_update } : {}) }, actor,
        selected.length ? '更新年度日历：' + selected.join('、') : '保存内网日历更新地址');
      setSelected([]);
      setSyncMessage(automatic ? '已保存，每周由后台自动同步；连接失败将在一小时后重试。' : '已保存，日历可离线使用。');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  return <Modal title="日历核查与内网更新" onClose={() => { if (!busy) onClose(); }} wide explicitClose>
    <div className="modal-body calendar-manager">
      <div className="calendar-actions">
        <label className="field"><span>内网日历服务地址</span><input className="input input-sm" type="url" aria-label="内网日历服务地址" placeholder="填写单位内网日历接口地址" value={sourceUrl} disabled={busy} onChange={e => { setSourceUrl(e.target.value); setSyncMessage(''); setPack(null); setSelected([]); }}/></label>
        <button type="button" className="btn btn-primary btn-sm" disabled={busy || !sourceUrl.trim()} onClick={syncCalendar}>{busy ? '正在检查…' : '检查内网更新'}</button>
      </div>
      <p className="fine">连接单位内网时检查更新，保存后离线核验。首次连接成功后，地址随日历一起保存。</p>
      <label className="checkline calendar-auto">
        <input type="checkbox" className="checkbox checkbox-sm" aria-label="每周自动同步服务器日历" checked={automatic} disabled={busy} onChange={e => {
          setAutomatic(e.target.checked);
          if (e.target.checked && pack?.fetched_from) setSelected(pack.calendars.map(c => c.year));
        }}/>
        <span>每周自动同步服务器日历，覆盖该服务提供的同年内容</span>
      </label>
      <p className="fine">需保持本工具服务运行。连接失败一小时后重试，已有日历可继续使用。自动更新后刷新台账可查看新结果。</p>
      {syncStatus?.url === state.calendar_update?.url && syncStatus?.checked_at && <p className="fine" role="status">
        上次后台检查 {new Date(syncStatus.checked_at).toLocaleString('zh-CN')} · {syncStatus.error || (syncStatus.changed_years?.length ? '已更新 ' + syncStatus.changed_years.join('、') + ' 年' : '服务器日历无变化')}
      </p>}
      {syncMessage && <p className="fine" role="status">{syncMessage}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <section className="calendar-view">
        <div className="calendar-controls">
          <label>年份<select aria-label="日历年份" className="select select-sm" value={year} onChange={e => setYear(Number(e.target.value))}>{Array.from({ length: 101 }, (_, i) => 2000 + i).map(y => <option key={y}>{y}</option>)}</select></label>
          <label>月份<select aria-label="日历月份" className="select select-sm" value={month} onChange={e => setMonth(Number(e.target.value))}>{Array.from({ length: 12 }, (_, i) => i + 1).map(m => <option key={m}>{m}</option>)}</select></label>
          <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onManual(year)}>维护本年度</button>
        </div>
        <p className="fine calendar-source">{current ? current.source : year + ' 年放假调休安排未维护，当前仅按周一至周五估算。'}</p>
        <div className="calendar-grid" role="table" aria-label={year + '年' + month + '月工作日历'}>
          {['一', '二', '三', '四', '五', '六', '日'].map(d => <strong role="columnheader" key={d}>周{d}</strong>)}
          {Array.from({ length: offset }, (_, i) => <span key={'empty' + i}/>)}
          {Array.from({ length: count }, (_, i) => {
            const date = new Date(Date.UTC(year, month - 1, i + 1));
            const day = calendarDay(date, state.calendars);
            return <div role="cell" key={i} className={day.work ? 'calendar-work' : 'calendar-rest'} title={day.key + ' ' + day.kind}>
              <span>{i + 1}</span><small>{day.kind}</small>
            </div>;
          })}
        </div>
      </section>
      <section className="calendar-range">
        <label className="field"><span>核查开始日期</span><input aria-label="核查开始日期" className="input input-sm" type="date" min="2000-01-01" max="2100-12-31" value={start} onChange={e => setStart(e.target.value)}/></label>
        <label className="field"><span>核查结束日期</span><input aria-label="核查结束日期" className="input input-sm" type="date" min="2000-01-01" max="2100-12-31" value={end} onChange={e => setEnd(e.target.value)}/></label>
        {summary ? <div className="calendar-range-result" role="status">
          <strong>{summary.days} 个日历天 · {summary.work} 个工作日</strong>
          <p>放假 {summary.holiday} 天，普通周末 {summary.weekend} 天，工作日中含补班 {summary.makeup} 天。</p>
          {summary.missing.length > 0 && <p>{summary.missing.join('、')} 年安排待补，以上为估算。</p>}
        </div> : <p role="alert">请选择完整且先后正确的核查日期。</p>}
      </section>
      <p className="fine">容量核验使用已保存的日历，保存更新后自动重算。休息日的实际投入仍需结合报工依据核实。</p>
      <form onSubmit={applyPackage} className="calendar-import">
        {pack && <><strong>{pack.fetched_from ? '内网更新预览' : '本机内置日历'} {pack.bundle_version && ' · 版本 ' + pack.bundle_version}</strong>
        <p className="fine">{pack.fetched_from ? (automatic ? '自动同步已选择服务器全部年度。' : '已勾选新增或有变化的年度。') : '已勾选尚未维护的年度。'}保存后替换所选年度，并保留更正历史。</p>
        <div className="calendar-package-years">{pack.calendars.map(c => <label className="checkline" key={c.year}>
          <input type="checkbox" className="checkbox checkbox-sm" disabled={busy || (automatic && !!pack.fetched_from)} checked={selected.includes(c.year)} onChange={e => setSelected(xs => e.target.checked ? [...xs, c.year] : xs.filter(y => y !== c.year))}/>
          <span>{c.year} 年 · {changeStatus(c)} · 放假 {c.holidays.length} 天 / 补班 {c.makeup_days.length} 天</span>
          <details><summary>来源与差异</summary><p className="fine">{c.source}</p>{dateChanges(c).map(line => <p className="fine" key={line}>{line}</p>)}</details>
        </label>)}</div></>}
        <div className="calendar-actions">
          <label className="field"><span>本次操作人（手工留痕）</span><input className="input input-sm" required value={actor} onChange={e => setActor(e.target.value)} disabled={busy}/></label>
          <button className="btn btn-primary btn-sm" disabled={(!selected.length && !sourceUrl.trim()) || busy}>{busy ? '处理中…' : selected.length ? '保存所选年度并重新核验' : '保存更新设置'}</button>
        </div>
      </form>
    </div>
    <footer><button className="btn" disabled={busy} onClick={onClose}>关闭</button></footer>
  </Modal>;
}
