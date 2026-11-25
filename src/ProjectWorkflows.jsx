import {unitLabel} from './units.js';
import React, {useState} from 'react';
import {recordId} from './recordId.js';
import {levels, newPersonProfile, personLabel} from './PersonQualifications.jsx';
import {ProjectEntryGrid, workFields} from './ProjectEntryGrid.jsx';
import {ClaimAppend, participatingClaim} from './ClaimAppend.jsx';
import {projectDateHint} from './projectDates.js';
import {ProjectDateField, useProjectDateFeedback} from './ProjectDateField.jsx';
import {ImportRepairPanel} from './ImportRepairPanel.jsx';
import './project-workflows.css';

const units=['工日','工时'];
const peopleFields=[['name','姓名'],['company','所属单位'],['code','工号'],['title','职称'],['title_from','职称有效开始','date'],['title_to','职称有效结束','date'],['title_source','职称证明依据']];
const billingFields=[['submitted_at','申报日期','date'],['grade','申报计费等级'],['price','申报单价（元）','number'],['price_unit','申报单价单位','select',units],['basis_title','合同对应职称'],['allowed_grade','依据允许等级'],['basis_price','依据单价（元）','number'],['basis_unit','依据单价单位','select',units],['basis_from','计价有效开始','date'],['basis_to','计价有效结束','date'],['basis_source','合同或计价依据']];
const blankRow=()=>({key:recordId(),person_id:'',person:{...newPersonProfile(),qualification_required:false},entry:{unit:'工时',price_unit:'工日',basis_unit:'工日',duplicate:'pending',status:'pending'}});
const rowWithDefaults=(common,placeholder=false)=>{const row=blankRow();return {...row,placeholder,person:{...row.person,company:common.company||''},entry:{...row.entry,...Object.fromEntries(Object.entries(common).filter(([k,v])=>k!=='company'&&v!==''&&v!=null))}};};
const money=(e,key,unit)=>e.amount!=null&&e[key]!=null&&e.unit===e[unit]?(e.amount*e[key]).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}):'待补 / 单位不同';
const excluded=e=>!participatingClaim(e);

async function encodeWorkbook(file){
  if(!file.name.toLowerCase().endsWith('.xlsx')||file.size>8_000_000)throw new Error('请选择8MB以内的.xlsx模板文件');
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(reader.result.split(',')[1]);
    reader.onerror=()=>reject(new Error('文件读取失败'));
    reader.readAsDataURL(file);
  });
}

function Field({spec,value,onChange,required=false}){
  const [key,label,type='text',options]=spec;
  return <label className="field"><span>{label}{required?' *':''}</span>{type==='select'?<select className="select" value={value[key]??''} onChange={e=>onChange(key,e.target.value)} required={required}><option value="">请选择</option>{options.map(o=><option key={o}>{o}</option>)}</select>:type==='textarea'?<textarea className="textarea" rows={3} value={value[key]??''} onChange={e=>onChange(key,e.target.value)}/>:<input className="input" type={type} value={value[key]??''} required={required} min={type==='number'?0:undefined} step={type==='number'?'any':undefined} onChange={e=>onChange(key,type==='number'?(e.target.value===''?null:Number(e.target.value)):e.target.value)}/>}</label>;
}

export function ProjectWizard({Modal,state,project,projectFields,actor,setActor,onSave,onClose,request,api}){
  const existing=!!project;
  const storageKey=`hours-import-pending:${api}:${project?.id||'new'}`;
  const [stashed]=useState(()=>{
    try{return JSON.parse(localStorage.getItem(storageKey)||'null');}catch{return null;}
  });
  const [draft,setDraft]=useState(project||stashed?.project||{id:recordId()});
  const {dateIssue,validateDates}=useProjectDateFeedback(draft);
  const changeProject=(key,value)=>setDraft(project=>({...project,[key]:value}));
  const [step,setStep]=useState(existing?2:1),[addPeople,setAddPeople]=useState(existing);
  const [common,setCommon]=useState({unit:'工时',price_unit:'工日',basis_unit:'工日',...project?.entry_defaults,...stashed?.common}),[importFile,setImportFile]=useState(null);
  const [rows,setRows]=useState(()=>[rowWithDefaults(common,true)]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[ack,setAck]=useState(false);
  const [importMessage,setImportMessage]=useState('');
  const [repairRows,setRepairRows]=useState(stashed?.rows||[]),[hasImported,setHasImported]=useState(!!stashed?.rows?.length);
  const [readingImages,setReadingImages]=useState(0);
  const updateRow=(key,section,field,value)=>{setAck(false);setRows(xs=>xs.map(r=>r.key===key?section?{...r,placeholder:false,[section]:{...r[section],[field]:value}}:{...r,placeholder:false,[field]:value}:r));};
  const updateProfile=(key,patch)=>{setAck(false);setRows(xs=>xs.map(r=>r.key===key?{...r,placeholder:false,person:{...r.person,...patch}}:r));};
  const selectPerson=(key,value)=>{
    setAck(false);
    setRows(xs=>xs.map(row=>row.key===key?{
      ...row,placeholder:false,person_id:value.startsWith('person:')?value.slice(7):'',manual:value==='new',
    }:row));
  };
  const commonEntries=Object.fromEntries(Object.entries(common).filter(([k,v])=>k!=='company'&&v!==''&&v!=null));
  const newRow=()=>rowWithDefaults(common);
  const changeCommon=(key,value)=>{setCommon(d=>({...d,[key]:value}));setError('');};
  const applyCommon=()=>{setRows(xs=>xs.map(r=>({...r,person:{...r.person,company:r.person.company||common.company||''},entry:{...commonEntries,...Object.fromEntries(Object.entries(r.entry).filter(([,v])=>v!==''&&v!=null))}})));setAck(false);};
  const presets=state.entries.filter(e=>e.project_id===draft.id&&!excluded(e)&&e.basis_source);
  const identity=r=>r.person_id||(r.person.code?.trim()?(state.people.find(p=>(p.company||'')===(r.person.company||'').trim()&&p.code===r.person.code.trim())?.id||`${(r.person.company||'').trim()}\u0000${r.person.code.trim()}`):null);
  const earlierProfile=(r,i)=>r.manual&&r.person.code?.trim()&&r.person.name?.trim()?rows.slice(0,i).find(x=>x.manual&&identity(x)===identity(r)&&x.person.name?.trim()===r.person.name.trim()):null;
  const claimGroups=new Map();
  for(const row of rows){
    const key=identity(row);
    if(!key||row.placeholder||(!row.person_id&&!row.manual))continue;
    if(!claimGroups.has(key)){
      const person=state.people.find(p=>p.id===key)||row.person;
      const entries=state.entries.filter(entry=>entry.project_id===draft.id&&entry.person_id===key);
      claimGroups.set(key,{key,label:personLabel(person),entries,batchCount:0});
    }
    claimGroups.get(key).batchCount++;
  }
  const appendGroups=[...claimGroups.values()].filter(group=>group.entries.length||group.batchCount>1);
  const appendIds=new Set(appendGroups.map(group=>group.key));
  async function upload(file){
    if(!file)return;
    setError('');
    setImportMessage('');
    setImportFile(file);
    setBusy(true);
    try{
      const encoded=await encodeWorkbook(file);
      const result=await request('/import-preview',{file:encoded,defaults:common});
      if(!result.rows.length&&result.errors.every(issue=>!issue.data)){
        setError(result.errors[0]?.message||'文件中没有申报记录');
        return;
      }
      const added=result.rows.map(importedRow);
      const pending=result.errors.filter(issue=>issue.data).map(issue=>({
        ...issue,key:recordId(),layout:result.layout,epoch:result.epoch,fields:result.fields,
      }));
      setRows(xs=>[...xs.filter(row=>!row.placeholder),...added]);
      setRepairRows(previous=>[...previous,...pending]);
      setHasImported(true);
      setAck(false);
      setImportFile(null);
      setImportMessage(`已通过 ${added.length} 行，待修改 ${pending.length} 行。确认保存后写入台账。`);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  function persistProblems(key=storageKey){
    if(repairRows.length)localStorage.setItem(key,JSON.stringify({project:draft,common,rows:repairRows}));
    else localStorage.removeItem(key);
  }
  function closeWizard(){
    try{persistProblems();onClose();}catch{setError('暂存空间不足，请先导出待修改行后再关闭。');}
  }
  function stashProblems(){
    try{persistProblems();setImportMessage('待修改行已暂存在本浏览器，重新打开本项目可继续。');}
    catch{setError('暂存空间不足，请导出待修改行。');}
  }
  async function exportProblems(){
    setBusy(true);setError('');
    try{
      const layouts=[...new Set(repairRows.map(item=>item.layout))];
      for(const layout of layouts){
        const items=repairRows.filter(item=>item.layout===layout);
        const records=items.map(item=>Object.fromEntries(item.fields.map(({key})=>[
          key,item.data[key]||String(common[key]??''),
        ])));
        const response=await fetch(`${api}/import-problems-export`,{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({layout,rows:records}),
        });
        if(!response.ok)throw new Error((await response.json()).error||'导出失败');
        const url=URL.createObjectURL(await response.blob());
        const link=document.createElement('a');link.href=url;
        link.download=`${draft.code||'项目'}-待修改行-${layout}.xlsx`;link.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
      }
      setImportMessage('已导出待修改行，补齐后可再次导入。已通过行已从导出中排除。');
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function checkImportRow(item,data){
    setBusy(true);
    setError('');
    try{
      const {layout,row,epoch}=item;
      const result=await request('/import-repair',{layout,row,epoch,data,defaults:common});
      if(result.errors.length){
        const feedback=result.errors[0];
        setRepairRows(previous=>previous.map(problem=>problem.key===item.key
          ? {...problem,issues:feedback.issues} : problem));
        return;
      }
      const corrected=importedRow(result.rows[0]);
      const earlier=rows.find(draft=>draft.manual&&corrected.manual&&identity(draft)===identity(corrected));
      const conflicts=earlier ? peopleFields
        .filter(([key])=>earlier.person[key]&&corrected.person[key]&&earlier.person[key]!==corrected.person[key])
        .map(([field,label])=>({field,message:`${label}与左栏同单位、同工号的人员资料不一致`})) : [];
      if(conflicts.length){
        setRepairRows(previous=>previous.map(problem=>problem.key===item.key ? {...problem,issues:conflicts} : problem));
        return;
      }
      setRows(previous=>[...previous.filter(draft=>!draft.placeholder),corrected]);
      setRepairRows(previous=>previous.filter(problem=>problem.key!==item.key));
      setImportMessage(`Excel 第 ${row} 行已通过，已移入左栏。`);
      setAck(false);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  function importedRow({data,person_id,row}){
    const draftRow=blankRow();
    const person={
      ...draftRow.person,
      ...Object.fromEntries(peopleFields.map(([key])=>[key,data[key]])),
      title_permanent:!data.title_from&&!data.title_to,
    };
    if(!person_id&&!levels.includes(person.title))person.title='';
    const entry=Object.fromEntries([...workFields,...billingFields].map(([key])=>[key,data[key]]));
    return {...draftRow,person_id:person_id||'',person:person_id?draftRow.person:person,
      entry:{...draftRow.entry,...entry},sourceRow:row,manual:!person_id};
  }
  async function submit(e){
    e.preventDefault();setError('');
    if(step===1){
      if(!validateDates(e.currentTarget))return;
      if(addPeople){setStep(2);return;}
    }
    const entries=addPeople?rows.filter(row=>!row.placeholder):[];
    if(readingImages)return;
    if(existing&&!entries.length){setError('请至少添加一条人员工时');return;}
    if(entries.some(row=>!row.person_id&&!row.manual)){setError('请为每条工时选择库内人员或手动填写人员资料');return;}
    if(addPeople&&appendGroups.length&&!ack){setError('请核对申报记录，并确认追加');return;}
    setBusy(true);
    try{
      const next=structuredClone(state);
      const savedProject={...draft,...(addPeople?{entry_defaults:common}:{})};
      if(!existing)next.projects.push(savedProject);
      else next.projects=next.projects.map(p=>p.id===draft.id?savedProject:p);
      const identities=new Map(next.people.map(p=>[`${p.company}\u0000${p.code}`,p]));
      for(const row of entries){
        let person=next.people.find(p=>p.id===row.person_id);
        if(!person){
          const profile=earlierProfile(row,rows.indexOf(row))?.person||row.person;
          const details=Object.fromEntries(Object.entries(profile).map(([k,v])=>[k,typeof v==='string'?v.trim():v]));
          if(!details.name||!details.code||!details.company)throw new Error('新增人员的姓名、工号和所属单位必填');
          if(!levels.includes(details.title))throw new Error('请选择新增人员的职称');
          const identity=`${details.company}\u0000${details.code}`;
          if(state.people.some(p=>p.company===details.company&&p.code===details.code))throw new Error('同单位工号已在库，请在第一列选择已有人员');
          person=identities.get(identity);
          if(person&&peopleFields.some(([k])=>details[k]&&details[k]!==person[k]))throw new Error('同单位工号的人员资料不一致，请选择已有人员或核对信息');
          if(!person){person={id:recordId(),...details};next.people.push(person);identities.set(identity,person);}
        }
        const {amount,unit,start,end}=row.entry;
        if(!Number.isFinite(amount)||amount<=0||!units.includes(unit)||!start||!end||start>end){
          throw new Error('请核对申报数量、单位和投入起止日期');
        }
        next.entries.push({...row.entry,id:row.key,person_id:person.id,project_id:draft.id,status:'pending',
          duplicate:appendIds.has(identity(row))?'append':'pending'});
      }
      persistProblems(`hours-import-pending:${api}:${draft.id}`);
      await onSave(next,actor,`${existing?'补录项目工时':'新增项目'}：${draft.name}，${entries.length} 条申报`);
      if(storageKey!==`hours-import-pending:${api}:${draft.id}`)localStorage.removeItem(storageKey);
      onClose();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <Modal title={existing?`${draft.name} · 录入 / Excel导入`:'新增项目'} onClose={()=>{if(!busy)closeWizard();}} explicitClose wide={step===2?'grid':true}><form onSubmit={submit}>
    <div className="modal-body project-wizard">
      {!existing&&<ol className="wizard-steps"><li className={step===1?'current':''}>1 项目信息</li><li className={step===2?'current':''}>2 人员工时（可选）</li></ol>}
      {step===1&&<p className="fine">{projectDateHint}</p>}
      {step===1?<><div className="form-grid">{projectFields.map(spec=>spec[2]==='date'
        ? <ProjectDateField key={spec[0]} field={spec[0]} label={spec[1]} value={draft[spec[0]]} issue={dateIssue} onChange={changeProject}/>
        : <Field key={spec[0]} spec={spec} value={draft} required={!!spec[4]} onChange={changeProject}/>)}</div><label className="checkline"><input className="checkbox checkbox-sm" type="checkbox" checked={addPeople} onChange={e=>setAddPeople(e.target.checked)}/>同时添加人员和工时</label><p className="fine">可仅保存项目，之后从项目行“录入 / 导入”或“录入工时”单独添加。</p></>:<>
        <div className="excel-suggestion"><div className="import-actions"><a className="btn btn-ghost btn-sm" href={`${api}/template`} download>下载模板</a><label className="btn btn-ghost btn-sm">导入 Excel<input aria-label="导入项目人员工时Excel" type="file" accept=".xlsx" disabled={busy} onChange={e=>{upload(e.target.files[0]);e.target.value='';}} hidden/></label>{importFile&&<button className="btn btn-ghost btn-sm" type="button" disabled={busy} onClick={()=>upload(importFile)}>按公共信息重新解析文件</button>}</div><details className="batch-options"><summary>批量导入的统一设置（可选）</summary>        <fieldset className="common-inputs" disabled={busy}><legend>公共信息 · 统一填一次</legend><div className="form-grid">{workFields.filter(([k])=>k!=='amount').map(spec=><Field key={spec[0]} spec={spec} value={common} onChange={changeCommon}/>)}</div><div className="import-actions"><button className="btn btn-ghost btn-sm" type="button" disabled={!draft.impl_start||!draft.impl_end} onClick={()=>{setCommon(d=>({...d,start:draft.impl_start,end:draft.impl_end}));}}>使用项目实施期</button><span className="fine">需确认各人的实际投入日期相同；个人有差异可在表格填写覆盖。</span></div><details className="form-details"><summary>统一单位、计费依据（可选）</summary><label className="field"><span>新人员的统一所属单位</span><input className="input" list="import-company-options" value={common.company||''} onChange={e=>changeCommon('company',e.target.value)}/><datalist id="import-company-options">{[...new Set(state.people.map(p=>p.company))].map(c=><option key={c} value={c}/>)}</datalist></label>{presets.length>0&&<label className="field"><span>选择本项目已有计费依据</span><select className="select" defaultValue="" onChange={e=>{const entry=e.target.value===''?null:presets[Number(e.target.value)];if(entry){setCommon(c=>({...c,...Object.fromEntries(billingFields.map(([k])=>[k,entry[k]??'']))}));}}}><option value="">请选择依据，不自动套用</option>{presets.map((e,i)=><option key={e.id} value={i}>{state.people.find(p=>p.id===e.person_id)?.name} · {e.grade||'等级待补'} · {e.price??'单价待补'}元/{e.price_unit||'单位待补'} · {e.basis_source}</option>)}</select></label>}<div className="form-grid">{billingFields.map(spec=><Field key={spec[0]} spec={spec} value={common} onChange={changeCommon}/>)}</div><p className="fine">只套用你确认适用的共同依据；各人职称从台账读取，缺失时仍待补。</p></details>{rows.length>0&&<button className="btn btn-ghost btn-sm" type="button" onClick={applyCommon}>补充列表空白项（保留已填值）</button>}</fieldset></details></div>
        {importMessage&&<p className="grid-import-message" role="status">{importMessage}</p>}
        <fieldset className="project-grid-fieldset" disabled={busy||readingImages>0}>
          <section className="import-ready">
          {hasImported&&<div className="import-ready-heading">
            <h3>已通过（{rows.filter(row=>row.sourceRow).length} 行）</h3>
          </div>}
          {rows.length>0&&
          <ProjectEntryGrid rows={rows} people={state.people} api={api} earlierProfile={earlierProfile}
            onSelect={selectPerson} onProfile={updateProfile}
            onEntry={(key,field,value)=>updateRow(key,'entry',field,value)}
            onReading={delta=>setReadingImages(count=>count+delta)}
            onRemove={key=>{setRows(xs=>xs.filter(row=>row.key!==key));setAck(false);}}/>}
          {hasImported&&!rows.length&&<p className="fine">通过检查的行会显示在这里。</p>}
          <button type="button" className="btn add-person-next" onClick={()=>{setRows(xs=>[...xs,newRow()]);setAck(false);}}>＋ 添加一行</button>
          </section>
          {hasImported&&<ImportRepairPanel items={repairRows} people={state.people} busy={busy} onCheck={checkImportRow}
            onEdit={(key,data)=>setRepairRows(previous=>previous.map(item=>item.key===key?{
              ...item,data,issues:item.issues.map(issue=>({...issue,replace:issue.replace&&data[issue.field]===item.data[issue.field]})),
            }:item))}
            onExport={exportProblems} onStash={stashProblems}
            onRemove={key=>{setRepairRows(previous=>previous.filter(item=>item.key!==key));setError('');}}/>}
        </fieldset>
        {appendGroups.length>0&&<ClaimAppend groups={appendGroups} checked={ack} onChange={setAck}/>}
      </>}
      {(step===2||!addPeople)&&<label className="field actor"><span>本次操作人（手工留痕）</span><input className="input" required value={actor} onChange={e=>setActor(e.target.value)}/></label>}
      {error&&<p className="error" role="alert">{error}</p>}
    </div><footer>{step===2&&!existing&&<button className="btn btn-ghost" type="button" disabled={busy} onClick={()=>setStep(1)}>上一步</button>}<button className="btn" type="button" disabled={busy} onClick={closeWizard}>取消</button><button className="btn btn-primary" disabled={busy||readingImages>0}>{busy?'处理中…':step===1&&addPeople?'下一步：人员工时':repairRows.length?'保存已通过行并暂存问题行':'保存并核验'}</button></footer>
  </form></Modal>;
}

export function ReviewExport({Modal,state,results,project,person,request,api,onClose,selectAll=false}){
  const [options,setOptions]=useState(null),[selected,setSelected]=useState(project?[project.id]:[]),[error,setError]=useState('');
  const [downloading,setDownloading]=useState(false);
  React.useEffect(()=>{let live=true;if(person)request(`/export-options?person=${encodeURIComponent(person.id)}`).then(x=>{if(live){setOptions(x);setSelected((selectAll?x.projects:x.projects.filter(p=>p.problem)).map(p=>p.id));}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[person?.id]);
  const params=new URLSearchParams();selected.forEach(id=>params.append('project',id));if(person)params.set('person',person.id);
  const included=state.entries.filter(e=>selected.includes(e.project_id)&&(!person||e.person_id===person.id));
  async function downloadPdf(){
    setError('');
    setDownloading(true);
    try {
      const pdfParams=new URLSearchParams(params);
      pdfParams.set('format','pdf');
      const response=await fetch(`${api}/export-scoped?${pdfParams}`);
      if(!response.ok)throw new Error((await response.json()).error||'PDF 导出失败');
      const url=URL.createObjectURL(await response.blob());
      const link=document.createElement('a');
      link.href=url;
      link.download=person?'人员工时核查报告.pdf':'项目工时核查报告.pdf';
      link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch(e) {
      setError(e.message);
    } finally {
      setDownloading(false);
    }
  }
  return <Modal title={project?`${project.name} · 项目核查导出`:`${person.name} · 人员核查导出`} onClose={onClose} wide><div className="modal-body export-review">
    {person&&<><p>参与 {options?.projects.length??'…'} 个项目。{selectAll?'已勾选此人的全部项目，可调整。':'默认勾选有预警或待补事项的项目，可调整。'}</p><div className="import-actions"><button className="btn btn-sm" onClick={()=>setSelected(options?.projects.map(p=>p.id)||[])}>全选</button><button className="btn btn-ghost btn-sm" onClick={()=>setSelected(options?.projects.filter(p=>p.problem).map(p=>p.id)||[])}>仅选有问题项目</button><button className="btn btn-ghost btn-sm" onClick={()=>setSelected([])}>清空选择</button></div><div className="export-projects">{options?.projects.map(p=><label className="checkline" key={p.id}><input className="checkbox checkbox-sm" type="checkbox" checked={selected.includes(p.id)} onChange={e=>setSelected(xs=>e.target.checked?[...xs,p.id]:xs.filter(id=>id!==p.id))}/><span>{p.name}（{p.code}） · {p.count} 条申报 {p.problem?'· 预警 / 待补':''}</span></label>)}</div>{options&&!options.projects.some(p=>p.problem)&&<p className="fine">没有默认勾选的项目，请手动选择需要导出的项目。</p>}</>}
    <p>已选 {selected.length} 个项目，{new Set(included.map(e=>e.person_id)).size} 人，{included.length} 条申报。</p>
    <div className="table-scroll"><table className="table table-sm"><thead><tr><th>人员 / 项目</th><th>申报量</th><th>申报金额（元）</th><th>依据测算（元）</th><th>工期核查</th><th>计费核查</th></tr></thead><tbody>{included.map(e=>{const r=results.find(r=>r.person.id===e.person_id);const fs=r?.findings.filter(f=>f.entry_id===e.id)||[];const warnings=r?.windows.some(w=>w.rank>0&&w.entry_ids.includes(e.id));return <tr key={e.id}><td>{r?.person.name}<small>{state.projects.find(p=>p.id===e.project_id)?.name}</small></td><td>{e.amount??'待补'} {unitLabel(e.unit)}</td><td>{money(e,'price','price_unit')}</td><td>{money(e,'basis_price','basis_unit')}</td><td>{excluded(e)?'不参与':fs.some(f=>f.category!=='职称计费')?'待核 / 待补':warnings?'关联窗口预警':'已提供字段未见异常'}</td><td>{excluded(e)?'不参与':fs.some(f=>f.category==='职称计费')?'待核 / 待补':'已提供字段未见异常'}</td></tr>;})}</tbody></table></div>
    <p className="fine">PDF 按已确认的表格模板生成，先看结论和关键工时，再看待核实事项。全库累计覆盖当前台账中同一人员的全部有效申报。</p>{options?.person_findings.length>0&&<details><summary>人员整体核查背景</summary>{options.person_findings.map((f,i)=><p className="fine" key={i}>{f.message}</p>)}</details>}{error&&<p className="error" role="alert">{error}</p>}
  </div><footer><button className="btn" onClick={onClose}>关闭</button>{included.length>0&&<a className="btn btn-ghost" href={`${api}/export-scoped?${params}`} download>下载 CSV</a>}<button className="btn btn-primary" onClick={downloadPdf} disabled={!included.length||downloading}>{downloading?'正在生成…':'下载 PDF 报告'}</button></footer></Modal>;
}
