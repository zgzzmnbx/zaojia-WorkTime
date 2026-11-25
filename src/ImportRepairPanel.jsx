import React from 'react';

const dateFields = new Set(['start','end','title_from','title_to','submitted_at','basis_from','basis_to']);

function RepairRow({item, people, busy, onCheck, onRemove, onEdit}) {
  const draft = item.data;
  const setDraft = update => onEdit(item.key, typeof update === 'function' ? update(draft) : update);
  const errors = new Map();
  for (const issue of item.issues) {
    errors.set(issue.field, [...(errors.get(issue.field) || []), issue.message]);
  }
  const unchangedCellError = item.issues.some(issue => issue.replace && draft[issue.field] === item.data[issue.field]);
  function fieldControl({key, label}, index) {
    const messages = errors.get(key);
    const name = `${String.fromCharCode(65 + index)}${item.row} · ${label}`;
    return <div className="field import-repair-field" key={key}>
      <label htmlFor={item.key+'-'+key}>{name}</label>
      <input className={messages ? 'input input-error' : 'input'} id={item.key+'-'+key}
        aria-invalid={messages ? true : undefined} aria-describedby={messages ? item.key+'-'+key+'-error' : undefined}
        value={draft[key] ?? ''} placeholder={dateFields.has(key) ? '例如 2025/4/4' : undefined}
        onChange={event => setDraft(value => ({...value, [key]:event.target.value}))}/>
      {messages && <small id={item.key+'-'+key+'-error'} className="error">{messages.join('；')}</small>}
    </div>;
  }
  const fields = item.fields.map((field,index) => ({field,index}));
  const flagged = fields.filter(({field}) => errors.has(field.key));
  const others = fields.filter(({field}) => !errors.has(field.key));
  return <article className="import-repair-row">
    <h4>Excel 第 {item.row} 行{draft.name ? ` · ${draft.name}` : ''}</h4>
    {item.issues.filter(issue => !item.fields.some(field => field.key === issue.field)).map(issue =>
      <p key={issue.field} className="error">{issue.message}</p>)}
    {'person_choice' in draft && (errors.has('person_choice') || errors.has('code') || errors.has('name') || errors.has('company')) &&
      <label className="field"><span>从人员库重新选择</span>
        <select className="select" value="" onChange={event => {
          const choice = event.target.value;
          if (!choice) return;
          setDraft(value => {
            const next = {...value,person_choice:choice};
            if (choice !== '新增人员') {
              for (const key of ['name','code','company']) if (key in next) next[key] = '';
            }
            return next;
          });
        }}>
          <option value="">请选择</option>
          {item.layout !== 'compact' && <option>新增人员</option>}
          {people.map(person => <option key={person.id}>{`${person.name} · ${person.company || ''} · ${person.code}`}</option>)}
        </select>
      </label>}
    <div className="import-repair-fields">{flagged.map(({field,index}) => fieldControl(field,index))}</div>
    {others.length > 0 && <details>
      <summary>查看其他填报内容</summary>
      <div className="import-repair-fields">{others.map(({field,index}) => fieldControl(field,index))}</div>
    </details>}
    <div className="import-actions">
      <button type="button" className="btn btn-sm btn-primary" disabled={busy||unchangedCellError}
        onClick={() => onCheck(item,draft)}>检查此行</button>
      <button type="button" className="btn btn-sm btn-ghost" disabled={busy} onClick={() => onRemove(item.key)}>移除此行</button>
    </div>
  </article>;
}

export function ImportRepairPanel({items, people, busy, onCheck, onRemove, onEdit, onExport, onStash}) {
  return <section className="import-repair" aria-labelledby="import-repair-title">
    <h3 id="import-repair-title">待修改（{items.length} 行）</h3>
    {!!items.length && <div className="import-actions">
      <button type="button" className="btn btn-sm" disabled={busy} onClick={onStash}>暂存待修改行</button>
      <button type="button" className="btn btn-sm" disabled={busy} onClick={onExport}>导出待修改行</button>
    </div>}
    {items.length ? items.map(item => <RepairRow key={item.key} item={item} people={people}
      busy={busy} onCheck={onCheck} onRemove={onRemove} onEdit={onEdit}/>) : <p className="fine">所有导入行均已通过检查。</p>}
  </section>;
}
