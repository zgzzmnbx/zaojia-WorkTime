import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ChartBarHorizontal, Users, Buildings, ListChecks, ClockCounterClockwise, GearSix, Plus, Moon, Sun, MagnifyingGlass, X, DownloadSimple, UploadSimple, PencilSimple, Info, CheckCircle, WarningCircle, ArrowClockwise, Printer, CaretRight, Funnel, FloppyDisk } from '@phosphor-icons/react';
import './style.css';
import CapacityGauge from './CapacityGauge.jsx';
import Timeline from './FlowTimeline.jsx';
import './workbench.css';
import './fonts.css';
import './floating.css';
import ThemePicker from './ThemePicker.jsx';
import WindowContributions from './WindowContributions.jsx';
import { personRisk, riskExplanation, capacityExplanation, overlapPeriods, exactOverlapWindow, orderedWindows } from './timelineRisk.js';

import { version as VERSION } from '../package.json';
const demo=new URLSearchParams(location.search).get('demo')==='1';
const API=demo?'/api/demo':'/api';
const DAY=86400000, dn=s=>Date.parse(s+'T00:00:00Z')/DAY;
const iso=n=>new Date(n*DAY).toISOString().slice(0,10);
const md=s=>s?s.slice(5).replace('-','/'):'待补';
const num=v=>v==null?'—':Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2});
const excludedEntry=e=>['withdrawn','returned'].includes(e.status)||e.duplicate==='duplicate';
const entryNote=e=>e.duplicate==='duplicate'?'重复不计':['withdrawn','returned'].includes(e.status)?'已停用':'';
const units=['工日','工时','人月'];
const personSummary=r=>r.worst?.rank===0&&Object.values(r.checks).includes('需核查')?'期间 / 计费待核':r.worst?.label||'资料待补';
const clone=v=>structuredClone(v);
const Icon=({as:C,...props})=><C weight="duotone" size={20} aria-hidden="true" {...props}/>;
const badge=(text,kind='muted')=><span className={'badge badge-soft tag '+kind}>{text}</span>;

async function request(path,body){
  const r=await fetch(API+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  const data=await r.json(); if(!r.ok)throw new Error(data.error||'读取失败');return data;
}

function Modal({title,onClose,children,wide=false}){
  const ref=useRef();
  useEffect(()=>{const previous=document.activeElement;ref.current.showModal();return()=>previous?.focus();},[]);
  return <dialog className={'modal app-modal '+(wide?'wide':'')} ref={ref} onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===ref.current)onClose();}}>
    <div className="modal-box"><header><h2>{title}</h2><button className="btn btn-ghost icon" aria-label="关闭" onClick={onClose}><Icon as={X}/></button></header>{children}</div>
  </dialog>;
}

function Editor({spec,state,actor,setActor,onSave,onClose}){
  const [draft,setDraft]=useState(clone(spec.value));const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  const [dupAck,setDupAck]=useState(false);
  const peers=spec.kind==='entries'?state.entries.filter(x=>x.id!==draft.id&&x.person_id===draft.person_id&&x.project_id===draft.project_id&&x.status!=='withdrawn'):[];
  const update=(key,value)=>{setDraft(d=>({...d,[key]:value}));if(['person_id','project_id','start','end'].includes(key))setDupAck(false);};
  async function submit(e){e.preventDefault();setError('');
    if(peers.length&&!dupAck){setError('请确认同一项目已有申报的处理方式');return;}
    setBusy(true);try{await onSave(draft,actor);onClose();}catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const render=([key,label,type='text',opts,required=false])=><label className={'field '+(type==='textarea'?'span2':'')} key={key}><span>{label}{required&&<b className="required"> *</b>}</span>
    {type==='select'?<select className="select" value={draft[key]??''} required={required} onChange={e=>update(key,e.target.value)}><option value="">请选择</option>{opts.map(o=><option key={typeof o==='string'?o:o.value} value={typeof o==='string'?o:o.value}>{typeof o==='string'?o:o.label}</option>)}</select>:
    type==='textarea'?<textarea className="textarea" rows={3} value={draft[key]??''} required={required} onChange={e=>update(key,e.target.value)}/>:
    <input className="input" type={type} required={required} min={type==='number'?0:undefined} step={type==='number'?'any':undefined} value={draft[key]??''} onChange={e=>update(key,type==='number'?(e.target.value===''?null:Number(e.target.value)):e.target.value)}/>}</label>;
  return <Modal title={spec.title} onClose={()=>{if(!busy)onClose();}} wide><form onSubmit={submit}>
    <div className="modal-body"><div className="form-grid">{spec.fields.map(render)}</div>
      {spec.extra&&<details className="form-details"><summary>计费与合同依据</summary><div className="form-grid">{spec.extra.map(render)}</div></details>}
      {peers.length>0&&<div className="duplicate-box"><p>此人在该项目已有 {peers.length} 条申报：{peers.map(x=>num(x.amount)+x.unit+'（'+md(x.start)+'—'+md(x.end)+'）').join('、')}</p><label className="field"><span>本条如何处理</span><select className="select" value={draft.duplicate||'pending'} onChange={e=>update('duplicate',e.target.value)}><option value="pending">保留待核</option><option value="append">确认追加，参与累计</option><option value="duplicate">重复录入，保留但不计入</option></select></label><label className="checkline"><input className="checkbox checkbox-sm" type="checkbox" checked={dupAck} onChange={e=>setDupAck(e.target.checked)}/>已核对已有记录及本条处理方式</label></div>}
      <label className="field actor"><span>本次操作人（手工留痕）</span><input className="input" value={actor} required onChange={e=>setActor(e.target.value)}/></label>
      {error&&<div className="error" role="alert">{error}</div>}
    </div><footer><button type="button" className="btn" onClick={onClose} disabled={busy}>取消</button><button className="btn btn-primary" disabled={busy}><Icon as={FloppyDisk}/>{busy?'保存中…':'保存并核验'}</button></footer>
  </form></Modal>;
}

function Detail({result,scope,overlap,entryId,projects,onEdit,onPrint,onClose}){
  const entry=result.entries.find(e=>e.id===entryId);const w=overlap?null:entry?(scope?.entry_ids.includes(entryId)?scope:null):scope;
  const overlapWindow=exactOverlapWindow(overlap,result.windows);
  const check=result.entry_checks.find(x=>x.id===entryId);
  return <aside className="evidence"><div className="evidence-title"><h3>{entry?'申报依据':'核验依据'}</h3><button className="btn btn-ghost icon" aria-label="打印核验明细" title="打印核验明细" onClick={onPrint}><Icon as={Printer}/></button><button className="btn btn-ghost icon" aria-label="收起核验依据" title="收起核验依据" onClick={onClose}><Icon as={X}/></button></div>
    <div className="evidence-body">{entry?<>
      <div className="detail-project">{projects.find(p=>p.id===entry.project_id)?.name}</div><div className="detail-overview"><div className="detail-amount">{num(entry.amount)}<small>{entry.unit}</small></div><div className="detail-status">{entryNote(entry)&&badge(entryNote(entry))}<button className="btn btn-ghost btn-sm" onClick={()=>onEdit(entry)}><Icon as={PencilSimple} size={14}/>编辑</button></div></div><div className="detail-meta">{entry.start||'日期待补'} — {entry.end||'日期待补'}</div>
      {overlap?<p className="fine">当前查看{iso(overlap.start)}—{iso(overlap.end)}重叠段；本页数量是整条申报量。{overlapWindow?`该段完整申报合计${num(overlapWindow.demand)}工日。`:'跨出本段的申报不能直接作为本段工时。'}</p>:scope&&!w&&<p className="fine">本条不计入当前所选时段的合计。</p>}
      {w?.rank>=2&&<details className="detail-section" key={`related-${entry.id}-${w.start}-${w.end}`}><summary>相关时段累计</summary><p>{riskExplanation(w,result.rule_snapshot)}</p></details>}
      <div className="detail-section"><h4>本条核查</h4>{check?.findings.length?check.findings.map((f,i)=><p className="finding" key={i}><Icon as={f.level==='pending'?Info:WarningCircle} size={16}/>{f.message}</p>):<p className="muted">{excludedEntry(entry)?'此条不参与本轮筛查':'当前已提供的字段未见异常'}</p>}</div>
      <details className="detail-section" key={`pricing-${entry.id}`}><summary>计价来源</summary><p>{entry.basis_source||'待补合同或计价依据'}</p><dl><dt>申报单价</dt><dd>{num(entry.price)} 元/{entry.price_unit||'—'}</dd><dt>依据单价</dt><dd>{num(entry.basis_price)} 元/{entry.basis_unit||'—'}</dd></dl>{check?.price_delta>0&&<p>同单位价差测算：{num(check.price_delta)} 元（模拟）</p>}</details>
    </>:overlap?<div className="detail-section first"><p><span className="tag muted">重叠段</span> {iso(overlap.start)}—{iso(overlap.end)}</p><p>涉及{new Set(overlap.entries.map(e=>e.project_id)).size}个项目。{overlapWindow?`该段完整申报合计${num(overlapWindow.demand)}工日，模拟结果：${overlapWindow.label}。`:'该段实际工时未知，暂不能判断是否超量。'}</p>{overlap.entries.map(e=><p key={e.id}>{projects.find(p=>p.id===e.project_id)?.name}</p>)}<p className="fine">只有完整落入本段的申报可用于本段合计；跨出本段的申报不能按总量或天数直接分摊。</p></div>:<>
      <div className="detail-section first"><h4>三类检查</h4>{Object.entries(result.checks).map(([k,v])=><div className="check-row" key={k}><span>{k}</span>{badge(v,v==='未见异常'?'good':'attention')}</div>)}</div>
      {w&&<details className="detail-section" key={`window-${w.start}-${w.end}`}><summary>当前时段计算依据</summary><p>{riskExplanation(w,result.rule_snapshot)||`${w.start} — ${w.end}`}</p><dl><dt>合计申报</dt><dd>{num(w.demand)} 工日</dd><dt>常规容量</dt><dd>{num(w.c0)} 工日</dd><dt>加班参考线</dt><dd>{num(w.c1)} 工日</dd><dt>高负荷参考线</dt><dd>{num(w.c2)} 工日</dd></dl><p className="fine">{capacityExplanation(w,result.rule_snapshot)}采用{w.basis}。低于参考线也不代表实际投入已核实。</p></details>}
      {result.duplicate_scenario&&<div className="detail-section"><h4>重复情景</h4><p>假设待核组保留最大一条、已确认追加仍保留：{result.duplicate_scenario.label}。</p></div>}
      <div className="detail-section"><h4>待核事项 <span>{result.findings.length}</span></h4>{result.findings.length?result.findings.map((f,i)=><p className="finding" key={i}><Icon as={f.level==='pending'?Info:WarningCircle} size={16}/>{f.message}</p>):<p className="muted">已提供字段未见异常。</p>}</div>
      <details className="detail-section"><summary>规则与日历来源</summary><p>规则 v{result.rule_snapshot.rule_version} · 模拟</p><p>每日 {result.rule_snapshot.hours_per_day} 小时；月加班参考 {result.rule_snapshot.overtime_hours} 小时。</p>{result.calendar_sources.map(c=><p key={c.year}>{c.year}：{c.source}</p>)}</details>
    </>}</div></aside>;
}

function App(){
  const [data,setData]=useState(null),[error,setError]=useState(''),[view,setView]=useState('timeline');
  const [personId,setPersonId]=useState(''),[entryId,setEntryId]=useState(''),[search,setSearch]=useState(''),[filter,setFilter]=useState('all');
  const [modal,setModal]=useState(null),[toast,setToast]=useState(''),[actor,setActorRaw]=useState(localStorage.getItem('hours-actor')||(demo?'模拟审核员':''));
  const [dark,setDark]=useState(localStorage.getItem('hours-theme')==='dark');
  const [loading,setLoading]=useState(false);
  const [showEvidence,setShowEvidence]=useState(false);
  const [scopeKey,setScopeKey]=useState('');
  const [overlapKey,setOverlapKey]=useState('');
  const [walking,setWalking]=useState(false);
  const evidenceTrigger=useRef(null);
  function openEntry(id){evidenceTrigger.current=document.activeElement;setEntryId(id);setShowEvidence(true);}
  function closeEvidence(){setShowEvidence(false);requestAnimationFrame(()=>evidenceTrigger.current?.focus());}
  const setActor=v=>{setActorRaw(v);localStorage.setItem('hours-actor',v);};
  useEffect(()=>{document.documentElement.dataset.theme=dark?'dark':'light';localStorage.setItem('hours-theme',dark?'dark':'light');},[dark]);
  async function refresh(){setLoading(true);try{const d=await request('/state');setData(d);setError('');setPersonId(id=>d.state.people.some(p=>p.id===id)?id:(d.results[0]?.person.id||''));}catch(e){setError(e.message);}finally{setLoading(false);}}
  useEffect(()=>{refresh();},[]);
  useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),3500);return()=>clearTimeout(t);}},[toast]);
  const state=data?.state;
  const result=data?.results.find(r=>r.person.id===personId);
  const scope=result?.windows.find(w=>`${w.start}/${w.end}`===scopeKey)||result?.worst;
  const overlaps=result?overlapPeriods(result.entries):[];
  const selectedOverlap=overlaps.find(o=>`${o.start}/${o.end}`===overlapKey);
  const walkWindows=orderedWindows(result?.windows||[]);
  const walkIndex=walkWindows.findIndex(w=>w.start===scope?.start&&w.end===scope?.end);
  function selectOverlap(o){setWalking(false);setOverlapKey(`${o.start}/${o.end}`);setEntryId('');}
  function applyScope(w){setScopeKey(`${w.start}/${w.end}`);setEntryId('');setOverlapKey('');}
  function selectScope(w){setWalking(false);applyScope(w);}
  function startWalk(){if(!walkWindows.length)return;setWalking(true);applyScope(walkWindows[0]);setShowEvidence(false);requestAnimationFrame(()=>document.querySelector('.person-scroll')?.scrollTo({top:0,behavior:'instant'}));}
  function stepWalk(delta){const next=walkIndex+delta;if(next<0||next>=walkWindows.length)return;applyScope(walkWindows[next]);}
  function exitWalk(){setWalking(false);}
  function choosePerson(id){setPersonId(id);setEntryId('');setScopeKey('');setOverlapKey('');setWalking(false);}
  async function save(next,who,action,restore=false){await request(restore?'/restore':'/save',{state:next,revision:data.revision,actor:who,action});await refresh();setToast('已保存并重新核验');}
  const projectFields=[['code','项目编号','text',null,true],['name','项目名称','text',null,true],['build_start','建设开始','date'],['build_end','建设结束','date'],['impl_start','实施开始','date'],['impl_end','实施结束','date'],['impl_source','实施期确认依据','textarea']];
  const personFields=[['name','姓名','text',null,true],['code','工号','text',null,true],['company','所属单位','text',null,true],['title','职称'],['title_from','职称有效开始','date'],['title_to','职称有效结束','date'],['title_source','职称证明依据','textarea']];
  function edit(kind,value){
    const fresh=!value;let fields,title,extra;value=value||{id:crypto.randomUUID()};
    if(kind==='projects'){fields=projectFields;title=fresh?'新增项目':'编辑项目';}
    if(kind==='people'){fields=personFields;title=fresh?'新增人员':'编辑人员';}
    if(kind==='entries'){
      title=fresh?'录入工时':'编辑申报';
      value={person_id:personId||state.people[0]?.id,project_id:state.projects[0]?.id,unit:'工日',price_unit:'工日',basis_unit:'工日',duplicate:'pending',status:'pending',...value};
      // Old approval metadata stays in history; editing an active claim needs no approval.
      if(!['withdrawn','returned'].includes(value.status))value.status='pending';
      fields=[['person_id','人员','select',state.people.map(p=>({value:p.id,label:`${p.name} · ${p.company} · ${p.code}`})),true],['project_id','项目','select',state.projects.map(p=>({value:p.id,label:p.name})),true],['start','人员投入开始','date'],['end','人员投入结束','date'],['amount','申报数量','number'],['unit','申报单位','select',units,true],['submitted_at','申报日期','date'],['duplicate','重复处理','select',[{value:'pending',label:'保留待核'},{value:'append',label:'确认追加'},{value:'duplicate',label:'确认为重复，不计入'}],true]];
      extra=[['grade','申报计费等级'],['price','申报单价（元）','number'],['price_unit','申报单价单位','select',units],['basis_title','合同对应职称'],['allowed_grade','依据允许等级'],['basis_price','依据单价（元）','number'],['basis_unit','依据单价单位','select',units],['basis_from','计价依据有效开始','date'],['basis_to','计价依据有效结束','date'],['basis_source','合同或计价依据','textarea']];
    }
    setModal({type:'editor',kind,title,value,fields,extra});
  }
  async function saveEditor(value,who){const next=clone(state);const i=next[modal.kind].findIndex(x=>x.id===value.id);if(i<0)next[modal.kind].push(value);else next[modal.kind][i]=value;await save(next,who,modal.title+': '+(value.name||value.id));if(modal.kind==='entries'){choosePerson(value.person_id);setEntryId(value.id);setShowEvidence(true);}if(modal.kind==='people')choosePerson(value.id);}
  function settings(){setModal({type:'editor',kind:'config',title:'模拟规则设置',value:state.config,fields:[['hours_per_day','每工日小时数','number',null,true],['days_per_month','每人月折合工日（未确认留空）','number'],['overtime_hours','每月加班参考小时','number',null,true],['average_month','折算平均月天数','number',null,true],['tolerance','比较容差（工日）','number',null,true]]});}
  function calendar(){const old=state.calendars[0];setModal({type:'calendar',value:{year:old?.year||2026,source:old?.source||'',holidays:old?.holidays.join('\n')||'',makeup_days:old?.makeup_days.join('\n')||''},title:'维护年度日历',fields:[['year','年份','number',null,true],['source','日历来源与适用说明','text',null,true],['holidays','休息日（每行 YYYY-MM-DD）','textarea'],['makeup_days','调休补班日（每行 YYYY-MM-DD）','textarea']]});}
  function print(){setModal({type:'print'});}
  const nav=[['timeline','工时轨迹',ChartBarHorizontal],['people','人员',Users],['projects','项目',Buildings],['entries','申报记录',ListChecks],['history','更正记录',ClockCounterClockwise]];
  const list=(data?.results||[]).filter(r=>`${r.person.name} ${r.person.code} ${r.person.company}`.includes(search)&&(filter==='all'||(filter==='warning'?Object.values(r.checks).includes('需核查'):r.pending_count>0)));
  const allEntries=state?.entries.filter(e=>{const p=state.people.find(p=>p.id===e.person_id),j=state.projects.find(p=>p.id===e.project_id);return `${p?.name} ${j?.name}`.includes(search);})||[];
  const entryTable=(rows,compact=false)=><div className={`table-scroll ${compact?'timeline-entries':''}`}><table className="table table-sm" aria-label={compact?'当前人员申报明细':'工时申报记录'}><thead><tr><th>{compact?'项目':'人员 / 项目'}</th><th>投入期间</th><th className="numeric">申报量</th><th>操作</th></tr></thead><tbody>{rows.map((e,i)=>{const p=state.people.find(p=>p.id===e.person_id),j=state.projects.find(p=>p.id===e.project_id);return <tr key={e.id} className={entryId===e.id?'selected-row':''}><td><div className={compact?'entry-project':''}>{compact&&<span className="entry-index" aria-label={`申报${i+1}`}>{i+1}</span>}<button className="text-link" title={j?.name} onClick={()=>{choosePerson(e.person_id);openEntry(e.id);setView('timeline');}}>{j?.name}</button>{compact&&entryNote(e)&&badge(entryNote(e))}</div>{!compact&&<small>{p?.name} · {p?.code}{entryNote(e)&&badge(entryNote(e))}</small>}</td><td>{md(e.start)} — {md(e.end)}</td><td className="numeric">{num(e.amount)} {e.unit}</td><td><button className="btn btn-ghost btn-sm" aria-label={compact?`编辑${j?.name}申报`:undefined} onClick={()=>edit('entries',e)}>编辑</button></td></tr>;})}</tbody></table></div>;
  return <div className="app-shell">
    <header className="app-header navbar"><div className="brand"><Icon as={ChartBarHorizontal} size={25}/><strong>专家工时核验</strong></div><nav className="ledger-switch" aria-label="台账切换"><a className={'btn btn-ghost btn-sm'+(!demo?' is-current':'')} href="/" aria-current={!demo?'page':undefined} title="切换到实际台账">实际</a><a className={'btn btn-ghost btn-sm'+(demo?' is-current':'')} href="/?demo=1" aria-current={demo?'page':undefined} title="切换到模拟台账">模拟</a></nav><button className="btn btn-ghost icon ledger-info" title="数据与规则说明（当前使用模拟规则）" aria-label="查看数据与规则说明" onClick={()=>setModal({type:'about'})}><Icon as={Info} size={17}/></button><div className="header-space"/>{data&&<>{view!=='history'&&<label className="search"><Icon as={MagnifyingGlass} size={17}/><input aria-label="搜索" placeholder={view==='timeline'?'姓名、单位或工号':'搜索'} value={search} onChange={e=>setSearch(e.target.value)}/></label>}<button className="btn btn-ghost icon" aria-label="刷新台账" title="刷新台账" disabled={loading} onClick={refresh}><Icon as={ArrowClockwise}/></button><a className="btn btn-ghost icon" href={API+'/export'} aria-label="导出核验结果" title="导出核验结果"><Icon as={DownloadSimple}/></a></>}<ThemePicker/><button className="btn btn-ghost icon" title={dark?'切换亮色':'切换深色'} aria-label={dark?'切换亮色':'切换深色'} onClick={()=>setDark(v=>!v)}><Icon as={dark?Sun:Moon}/></button>{data&&<>{view==='projects'?<button className="btn btn-primary" onClick={()=>edit('projects')}><Icon as={Plus} size={17}/>新增项目</button>:view==='people'?<button className="btn btn-primary" onClick={()=>edit('people')}><Icon as={Plus} size={17}/>新增人员</button>:view!=='history'&&<button className="btn btn-primary" disabled={!state.people.length||!state.projects.length} title={!state.people.length||!state.projects.length?'请先新增人员和项目':'录入此人的项目工时'} onClick={()=>edit('entries')}><Icon as={Plus} size={17}/>录入工时</button>}</>}</header>
    <div className="shell-body"><nav className="rail" aria-label="主导航"><ul className="menu menu-md rail-menu">{nav.map(([id,label,C])=><li key={id}><button className={'rail-btn '+(view===id?'active':'')} title={label} aria-label={label} aria-current={view===id?'page':undefined} onClick={()=>{setView(id);setSearch('');}}><Icon as={C} size={23}/><span>{label}</span></button></li>)}</ul><div className="rail-footer"><button className="rail-btn" title="设置与备份" aria-label="设置与备份" onClick={()=>setModal({type:'tools'})}><Icon as={GearSix} size={23}/><span>设置</span></button><small>v{VERSION}</small></div></nav>
    <main>{error&&<div className="error global-error" role="alert">{error}<button className="btn btn-sm" onClick={refresh}>重试读取</button></div>}
    {!data?<div className="empty"><span className="loading loading-spinner"/>正在读取台账</div>:<>
      <h1 className="sr-only">{nav.find(n=>n[0]===view)?.[1]}</h1>
      {view==='timeline'&&<div className="timeline-workspace"><aside className="people-panel"><div className="people-filter"><Icon as={Funnel} size={16}/><select aria-label="人员筛选" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部人员</option><option value="warning">有核查事项</option><option value="pending">待补依据</option></select><button className="btn btn-ghost icon" title="新增人员" aria-label="新增人员" onClick={()=>edit('people')}><Icon as={Plus} size={16}/></button></div><div className="people-list">{list.map(r=><button className={'person-card card '+(personId===r.person.id?'active':'')} key={r.person.id} onClick={()=>choosePerson(r.person.id)}><div className="person-name"><span className="avatar-letter">{r.person.name.slice(-2)}</span><strong>{r.person.name}</strong><span className={'risk-dot rank-'+personRisk(r)}/></div><div className="person-company">{r.person.company} · {r.person.code}</div><div className="person-bottom"><span>{new Set(r.entries.map(e=>e.project_id)).size} 项目</span><span className={`badge badge-sm person-risk-text rank-${personRisk(r)}`}>{personSummary(r)}</span></div>{r.pending_count>0&&<small className="pending-label">{r.pending_count} 项待补依据</small>}</button>)}{!list.length&&<div className="empty compact">暂无匹配人员</div>}</div></aside>
      {result?<><div className="person-workspace"><div className="person-scroll"><Timeline key={personId} entries={result.entries} projects={state.projects} windows={result.windows} scope={scope} selectScope={selectScope} overlaps={overlaps} selectedOverlap={selectedOverlap} selectOverlap={selectOverlap} walking={walking} walkIndex={walkIndex} walkCount={walkWindows.length} startWalk={startWalk} stepWalk={stepWalk} exitWalk={exitWalk} rules={result.rule_snapshot} calendars={state.calendars} onRisk={value=>setModal({type:'risk-window',value})} selectedId={entryId} onSelect={openEntry} onOverlap={value=>setModal(value?{type:'overlap',value}:{type:'chart-help'})} heading={<div className="person-inline"><h2 title={`${result.person.company} / ${result.person.code} / ${result.person.title||'职称待补'}`}>{result.person.name}</h2><button ref={evidenceTrigger} className="btn btn-ghost btn-sm summary-toggle" aria-label="查看完整核验依据" aria-expanded={showEvidence} onClick={()=>{setEntryId('');setShowEvidence(v=>!v);}}>{selectedOverlap?badge(exactOverlapWindow(selectedOverlap,result.windows)?.label||'重叠段待核'):badge(scope?.label||'无法判断','rank-'+(scope?.rank??'none'))}<Icon as={Info} size={16}/></button></div>}/>
        {entryTable(result.entries,true)}
</div>
      </div>{showEvidence&&<Detail result={result} scope={scope} overlap={selectedOverlap} entryId={entryId} projects={state.projects} onEdit={e=>edit('entries',e)} onPrint={print} onClose={closeEvidence}/>}</>:<div className="empty onboarding"><Icon as={ChartBarHorizontal} size={48}/><h2>从第一个项目的人员投入开始</h2><p>建立人员与项目，再逐条录入工时，形成跨项目轨迹。</p><div><button className="btn" onClick={()=>edit('projects')}>新增项目</button><button className="btn btn-primary" onClick={()=>edit('people')}>新增人员</button></div><a className="text-link" href="/?demo=1">先看模拟案例</a></div>}</div>}
      {view==='people'&&<div className="page-scroll"><table className="table table-sm"><thead><tr><th>姓名</th><th>单位 / 工号</th><th>职称 / 有效期</th><th>三类检查</th><th/></tr></thead><tbody>{list.map(r=><tr key={r.person.id}><td><button className="text-link" onClick={()=>{choosePerson(r.person.id);setView('timeline');}}>{r.person.name}</button></td><td>{r.person.company}<small>{r.person.code}</small></td><td>{r.person.title||'待补'}<small>{r.person.title_from||'—'} 至 {r.person.title_to||'—'}</small></td><td>{Object.entries(r.checks).map(([k,v])=><small key={k}>{k}：{v}</small>)}</td><td><button className="btn btn-ghost btn-sm" onClick={()=>edit('people',r.person)}>编辑</button></td></tr>)}</tbody></table></div>}
      {view==='projects'&&<div className="page-scroll"><table className="table table-sm"><thead><tr><th>项目</th><th>建设期间</th><th>实施期间</th><th>投入人员</th><th/></tr></thead><tbody>{state.projects.filter(p=>`${p.name} ${p.code}`.includes(search)).map(p=><tr key={p.id}><td><strong>{p.name}</strong><small>{p.code}</small></td><td>{p.build_start||'—'}<small>至 {p.build_end||'—'}</small></td><td>{p.impl_start||'—'}<small>至 {p.impl_end||'—'}</small></td><td><div className="project-people">{state.people.filter(u=>state.entries.some(e=>e.project_id===p.id&&e.person_id===u.id)).map(u=><button className="text-link" key={u.id} onClick={()=>{choosePerson(u.id);setView('timeline');}}>{u.name}（{u.code}）</button>)}</div></td><td><button className="btn btn-ghost btn-sm" onClick={()=>edit('projects',p)}>编辑</button></td></tr>)}</tbody></table></div>}
      {view==='entries'&&<div className="page-scroll">{entryTable(allEntries)}</div>}
      {view==='history'&&<div className="page-scroll"><table className="table table-sm"><thead><tr><th>版本</th><th>时间</th><th>操作人</th><th>更正事项</th><th>证据</th></tr></thead><tbody>{data.history.map(h=><tr key={h.revision}><td>r{h.revision}</td><td>{new Date(h.at).toLocaleString('zh-CN')}</td><td>{h.actor}</td><td>{h.action}</td><td><button className="btn btn-ghost btn-sm" onClick={async()=>{try{const x=await request('/history/'+h.revision);setModal({type:'history',value:x.state,revision:h.revision});}catch(e){setError(e.message);}}}>查看快照</button></td></tr>)}</tbody></table></div>}
    </>}</main></div>{toast&&<div className="toast toast-end" role="status"><div className="alert">{toast}</div></div>}
    {modal?.type==='about'&&<Modal title="数据与规则说明" onClose={()=>setModal(null)}><div className="modal-body"><p>{demo?'本页人物、项目、工时、合同和日历均为模拟数据，与业务台账隔离。':'本页为业务台账，与模拟案例分库保存。'}录入即参与校验，编辑保存后重新计算；当前规则仅用于模拟筛查。</p>{data&&<p>已保存至本地服务 · 修订 r{data.revision}<br/>{state.projects.length} 项目 / {state.people.length} 人 / {state.entries.length} 条申报</p>}</div></Modal>}
    {modal?.type==='chart-help'&&<Modal title="轨迹图说明" onClose={()=>setModal(null)}><div className="modal-body"><p>蓝色项目条表示原始投入期间，数量是整条申报量。整条蓝色深浅和底部刻纹疏密表示整段平均密度，颜色越深、底部刻纹越密表示每个日历天平均申报的工日越多；均值按完整申报工日除以含首尾的日历天数计算，工时和人月沿用当前模拟规则换算。底部刻纹仅作疏密示意，不代表实际逐日投入，也不参与重叠分摊或预警计算。下方每一行括线是一个独立累计范围；点击合计标签，参与项目通过连线接入右侧对应算式项，未参与项目保留原位并标记未计入。</p><p>风险小标签表示当前核查窗口相对模拟参考线的结果，不代表单个项目违规，也不是正式审减结论。不同累计范围可能互相包含，合计不能再次相加。</p><p>默认视图固定显示完整内容；使用左下角按钮放大后，可拖动空白处查看。缩回原比例或点击“适合窗口”恢复完整视图。“逐步演示”按日期顺序逐一展示各范围的来源、参考线与超出量。项目日期及数量不能通过拖动修改，需要在录入或编辑表单中更正。</p></div></Modal>}
    {modal?.type==='editor'&&<Editor spec={modal} state={state} actor={actor} setActor={setActor} onClose={()=>setModal(null)} onSave={modal.kind==='config'?async(v,a)=>save({...clone(state),config:v},a,'修改模拟规则'):saveEditor}/>}
    {modal?.type==='calendar'&&<Editor spec={modal} state={state} actor={actor} setActor={setActor} onClose={()=>setModal(null)} onSave={async(v,a)=>{const next=clone(state);const c={...v,holidays:v.holidays.split(/\s+/).filter(Boolean),makeup_days:v.makeup_days.split(/\s+/).filter(Boolean)};next.calendars=next.calendars.filter(x=>x.year!==c.year).concat(c);await save(next,a,'维护'+c.year+'年日历');}}/>}
    {modal?.type==='tools'&&<Modal title="设置与备份" onClose={()=>setModal(null)}><div className="modal-body tools"><button className="tool-row" onClick={settings}><Icon as={GearSix}/><span><strong>模拟规则</strong><small>工时换算、容量参考线、容差</small></span><Icon as={CaretRight}/></button><button className="tool-row" onClick={calendar}><Icon as={ListChecks}/><span><strong>年度日历</strong><small>休息日、补班日及来源</small></span><Icon as={CaretRight}/></button><a className="tool-row" href={API+'/backup'}><Icon as={DownloadSimple}/><span><strong>导出台账备份</strong><small>人员、项目、申报、规则与日历</small></span></a><label className="tool-row"><Icon as={UploadSimple}/><span><strong>恢复台账备份</strong><small>恢复前自动保留当前台账副本</small></span><input type="file" accept=".json" className="file-input file-input-sm" onChange={async e=>{try{const file=e.target.files[0];if(!file)return;const b=JSON.parse(await file.text());if(b.schema_version!==1||!b.state)throw new Error('不是有效的台账备份');setModal({type:'restore',value:b.state});}catch(e){setError(e.message);}}}/></label><p className="fine">本版按模拟参数筛查，人工处理记录不等同正式签字。原申报、更正版本及恢复记录保存在本地服务中。</p></div></Modal>}
    {modal?.type==='restore'&&<RestoreModal value={modal.value} actor={actor} setActor={setActor} onClose={()=>setModal(null)} onSave={async()=>{await save(modal.value,actor,'从备份恢复台账',true);setModal(null);}}/>}
    {modal?.type==='risk-window'&&<Modal title={`${modal.value.label} · 模拟容量核验`} onClose={()=>setModal(null)}><div className="modal-body"><WindowContributions window={modal.value} entries={result.entries} projects={state.projects} rules={result.rule_snapshot}/><CapacityGauge window={modal.value} rules={result.rule_snapshot}/>{modal.value.rank>0&&<p className="risk-detail-explanation">{riskExplanation(modal.value,result.rule_snapshot)}</p>}<p className="fine">{capacityExplanation(modal.value,result.rule_snapshot)}</p>{modal.value.entry_ids.map(id=>{const e=result.entries.find(x=>x.id===id);return e&&<div className="overlap-entry" key={id}><span>{state.projects.find(p=>p.id===e.project_id)?.name}</span><strong>{num(e.amount)} {e.unit}</strong></div>;})}<p className="fine">颜色依据整个核查窗口的容量结果，不表示每天实际投入；相关项目也不因此单独被判超量。</p><button className="btn btn-primary" onClick={()=>{selectScope(modal.value);setShowEvidence(true);setModal(null);}}>查看完整核验依据</button></div></Modal>}
    {modal?.type==='overlap'&&<Modal title="跨项目期间交叉" onClose={()=>setModal(null)}><div className="modal-body"><h3>{iso(modal.value.start)} — {iso(modal.value.end)}</h3><p className="muted">下列申报的可投入期间交叉；这些总量不能直接分摊为该交叉时段的实际工时。</p>{modal.value.entries.map(e=><div className="overlap-entry" key={e.id}><span>{state.projects.find(p=>p.id===e.project_id)?.name}</span><strong>全期 {num(e.amount)} {e.unit}</strong></div>)}<button className="btn btn-primary" disabled={!scope} onClick={()=>{if(scope)selectScope(scope);setShowEvidence(true);setModal(null);}}>查看整段累计核验</button></div></Modal>}
    {modal?.type==='history'&&<Modal title={'历史快照 r'+modal.revision} onClose={()=>setModal(null)} wide><div className="modal-body"><p className="muted">历史只读，可核对每次编辑前后的录入数据。</p><pre>{JSON.stringify(modal.value,null,2)}</pre></div></Modal>}
    {modal?.type==='print'&&result&&<Modal title="人员核验明细" onClose={()=>setModal(null)} wide><div className="modal-body printable"><h2>{result.person.name} · 人员工时核验</h2><p>{result.person.company} / {result.person.code} · 台账r{data.revision} · 模拟规则v{result.rule_snapshot.rule_version}</p><p>本报告按录入数据进行模拟筛查。{demo?'本报告全部为模拟数据。':''}</p>{Object.entries(result.checks).map(([k,v])=><p key={k}>{k}：{v}</p>)}{entryTable(result.entries)}<h3>核查依据</h3>{result.findings.map((f,i)=><p key={i}>{f.category}：{f.message}</p>)}{result.worst&&<p>{riskExplanation(result.worst,result.rule_snapshot)||`最紧时段：${result.worst.start}—${result.worst.end}，申报${num(result.worst.demand)}工日，常规容量${num(result.worst.c0)}，高负荷参考线${num(result.worst.c2)}。`}</p>}<p>参数快照：每工日 {result.rule_snapshot.hours_per_day} 小时；每人月折合工日 {result.rule_snapshot.days_per_month??"未配置"}；月加班参考 {result.rule_snapshot.overtime_hours} 小时；平均月天数 {result.rule_snapshot.average_month}；比较容差 {result.rule_snapshot.tolerance} 工日。</p>{result.calendar_sources.map(c=><p key={c.year}>日历来源 {c.year}：{c.source}</p>)}</div><footer><button className="btn btn-primary" onClick={()=>window.print()}>打印 / 保存 PDF</button></footer></Modal>}
  </div>;
}

function RestoreModal({value,actor,setActor,onClose,onSave}){
  const [error,setError]=useState(''),[busy,setBusy]=useState(false);
  return <Modal title="确认恢复台账" onClose={onClose}><form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await onSave();}catch(e){setError(e.message);}finally{setBusy(false);}}}><div className="modal-body"><p>将用备份中的 {value.projects?.length??'?'} 个项目、{value.people?.length??'?'} 名人员、{value.entries?.length??'?'} 条申报替换当前台账。服务端先保留恢复前副本，并新增更正记录。</p><label className="field"><span>操作人</span><input className="input" required value={actor} onChange={e=>setActor(e.target.value)}/></label>{error&&<p className="error" role="alert">{error}</p>}</div><footer><button type="button" className="btn" onClick={onClose}>取消</button><button className="btn btn-primary" disabled={busy}>{busy?'恢复中…':'确认恢复'}</button></footer></form></Modal>;
}

createRoot(document.getElementById('root')).render(<App/>);
