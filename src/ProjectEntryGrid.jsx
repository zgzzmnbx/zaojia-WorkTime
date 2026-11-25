import React, {useState} from 'react';
import {CertificateInput, CertificatePreview, levels} from './PersonQualifications.jsx';

export const workFields = [
  ['amount', '申报数量', 'number'],
  ['unit', '申报单位', 'select', ['工日', '工时']],
  ['start', '投入开始', 'date'],
  ['end', '投入结束', 'date'],
];

function PersonSelect({people, row, label, onSelect}) {
  const [search, setSearch] = useState('');
  const terms = search.trim().toLowerCase().split(/\s+/);
  const matches = people.filter(person => person.id === row.person_id ||
    terms.every(term => [person.name, person.company, person.code].join(' ').toLowerCase().includes(term)));
  return <div className="grid-person-select">
    <select className="select" aria-label={label('选择人员')}
      value={row.person_id ? 'person:' + row.person_id : row.manual ? 'new' : ''}
      onChange={event => { onSelect(event.target.value); setSearch(''); }}>
      <option value="">请选择</option>
      <option value="new">＋ 新增人员</option>
      {matches.length > 0 && <optgroup label="已有人员">
        {matches.map(person => <option key={person.id} value={'person:' + person.id}>
          {[person.name, person.company, person.code].filter(Boolean).join(' · ')}
        </option>)}
      </optgroup>}
    </select>
    {!row.person_id && !row.manual && <input className="input" type="search" aria-label={label('搜索人员')}
      placeholder="按姓名或工号筛选" value={search} onChange={event => setSearch(event.target.value)}
      onKeyDown={event => { if (event.key === 'Enter') event.preventDefault(); }}/>}
    {search && !matches.length && <small role="status">未找到，可选「新增人员」</small>}
  </div>;
}

function validity(person) {
  if (person.title_permanent) return '长期有效';
  return [person.title_from, person.title_to].filter(Boolean).join(' 至 ') || '待补';
}

export function ProjectEntryGrid({rows, people, api, earlierProfile, onSelect, onProfile, onEntry, onRemove, onReading}) {
  const peopleById = new Map(people.map(person => [person.id, person]));
  return <div className="project-grid-scroll" role="region" aria-label="人员工时录入表" tabIndex={0}>
    <table className="project-entry-grid">
      <colgroup>
        <col className="grid-col-index"/><col className="grid-col-person"/><col className="grid-col-name"/>
        <col className="grid-col-code"/><col className="grid-col-company"/><col className="grid-col-title"/>
        <col className="grid-col-validity"/><col className="grid-col-certificate"/>
        <col className="grid-col-amount"/><col className="grid-col-unit"/>
        <col className="grid-col-date"/><col className="grid-col-date"/><col className="grid-col-action"/>
      </colgroup>
      <thead><tr>
        <th scope="col">序号</th><th scope="col">选择人员</th><th scope="col">姓名</th><th scope="col">工号</th>
        <th scope="col">单位</th><th scope="col">职称</th><th scope="col">有效期</th>
        <th scope="col">职称证明</th>
        {workFields.map(([key, name]) => <th scope="col" key={key}>{name}</th>)}
        <th scope="col">操作</th>
      </tr></thead>
      <tbody>{rows.map((row, index) => {
        const saved = peopleById.get(row.person_id);
        const prior = earlierProfile(row, index)?.person;
        const person = saved || prior || row.person;
        const label = name => `第 ${index + 1} 行 ${name}`;
        const change = patch => onProfile(row.key, patch);
        const identityFields = [['name', '姓名'], ['code', '工号'], ['company', '单位']];
        return <tr key={row.key}>
          <th scope="row">{index + 1}{row.sourceRow && <small title={`Excel 第 ${row.sourceRow} 行`}>Excel {row.sourceRow}</small>}</th>
          <td><PersonSelect people={people} row={row} label={label} onSelect={value => onSelect(row.key, value)}/></td>
          {identityFields.map(([key, name]) => <td key={key} className={row.manual ? '' : 'grid-lookup'}>
            {row.manual ? <input className="input" aria-label={label(name)} value={row.person[key] ?? ''}
              required onChange={event => change({[key]: event.target.value})}/> : saved?.[key] || '—'}
          </td>)}
          <td className={row.manual && !prior ? '' : 'grid-lookup'}>
            {row.manual && !prior ? <select className="select" aria-label={label('职称')} required
              value={person.title || ''} onChange={event => change({title: event.target.value})}>
              <option value="">请选择</option>
              {levels.map(level => <option key={level}>{level}</option>)}
            </select> : person.title || '—'}
          </td>
          <td className={row.manual && !prior ? '' : 'grid-lookup'}>
            {row.manual && !prior ? <>
              <select className="select" aria-label={label('有效期')} value={person.title_permanent ? 'long' : 'dated'}
                onChange={event => change(event.target.value === 'long'
                  ? {title_permanent: true, title_from: '', title_to: ''} : {title_permanent: false})}>
                <option value="long">长期有效</option><option value="dated">指定期限</option>
              </select>
              {!person.title_permanent && <div className="grid-validity-dates">
                <input className="input" type="date" aria-label={label('证书有效开始')} required
                  value={person.title_from || ''} onChange={event => change({title_from: event.target.value})}/>
                <input className="input" type="date" aria-label={label('证书有效结束')} required
                  value={person.title_to || ''} onChange={event => change({title_to: event.target.value})}/>
              </div>}
            </> : saved || prior ? validity(person) : '—'}
          </td>
          <td className={row.manual && !prior ? '' : 'grid-lookup'}>
            {row.manual && !prior && <CertificateInput label={label('上传职称证明（选填）')} onReading={onReading} onChange={change}/>}
            {person.certificate_id ? <CertificatePreview person={person} api={api}/>
              : person.title_source || (row.manual && !prior ? <small>选填</small> : '—')}
          </td>
          {workFields.map(([key, name, type, options]) => <td key={key} className="grid-claim">
            {type === 'select'
              ? <select className="select" aria-label={label(name)} value={row.entry[key] ?? ''}
                required={!row.placeholder} onChange={event => onEntry(row.key, key, event.target.value)}>
                <option value="">请选择</option>{options.map(unit => <option key={unit}>{unit}</option>)}
              </select>
              : <input className="input" aria-label={label(name)} type={type} value={row.entry[key] ?? ''}
                min={type === 'number' ? 0 : undefined} step={type === 'number' ? 'any' : undefined}
                required={!row.placeholder} onChange={event => {
                  const value = event.target.value;
                  onEntry(row.key, key, type === 'number' ? (value === '' ? null : Number(value)) : value);
                }}/>}
          </td>)}
          <td><button type="button" className="btn btn-ghost btn-sm" aria-label={label('移除')} onClick={() => onRemove(row.key)}>移除</button></td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}
