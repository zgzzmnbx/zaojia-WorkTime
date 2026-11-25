import React, {useState} from 'react';
import './record-deletion.css';

const labels={projects:'项目',people:'人员',entries:'申报'};
function recordName(kind,record,state){
  if(kind!=='entries')return `${record.name}（${record.code}）`;
  const person=state.people.find(p=>p.id===record.person_id)?.name||'人员';
  const project=state.projects.find(p=>p.id===record.project_id)?.name||'项目';
  return `${person} · ${project} · ${record.amount??'待补'} ${record.unit}`;
}

export function DeleteRecordModal({Modal,kind,record,state,actor,setActor,onConfirm,onClose}){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const key={projects:'project_id',people:'person_id'}[kind];
  const count=key?state.entries.filter(e=>e[key]===record.id).length:0;
  const close=()=>{if(!busy)onClose();};
  async function submit(e){
    e.preventDefault();setBusy(true);setError('');
    try{await onConfirm();}catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <Modal title={`删除${labels[kind]}`} onClose={close} explicitClose>
    <form onSubmit={submit}><div className="modal-body deletion-body">
      <p className="deletion-name">{recordName(kind,record,state)}</p>
      <p>{kind==='entries'?'此条申报将从台账中移除，并重新核验。':`将同时移除该${labels[kind]}的 ${count} 条工时申报，并重新核验。`}</p>
      <p className="fine">删除后可在“已删除记录”中恢复，操作会留在更正记录中。</p>
      <label className="field actor"><span>操作人 *</span><input className="input" required value={actor} disabled={busy} onChange={e=>setActor(e.target.value)}/></label>
      {error&&<p className="error" role="alert">{error}</p>}
    </div><footer><button type="button" className="btn" disabled={busy} onClick={close}>取消</button><button className="btn btn-delete" disabled={busy}>{busy?'删除中…':'确认删除'}</button></footer></form>
  </Modal>;
}

export function DeletedRecordsModal({Modal,state,actor,setActor,onRestore,onClose}){
  const [busy,setBusy]=useState(''),[error,setError]=useState('');
  const items=state.deleted_records||[];
  async function restore(id){
    if(!actor.trim()){setError('请填写操作人');return;}
    setBusy(id);setError('');
    try{await onRestore(id);}catch(e){setError(e.message);}finally{setBusy('');}
  }
  return <Modal title="已删除记录" onClose={()=>{if(!busy)onClose();}} wide>
    <div className="modal-body deleted-records">
      <p className="fine">恢复时会一并恢复关联申报，并重新核验。若关联项目或人员也被删除，请先恢复它们。</p>
      {items.length>0&&<label className="field"><span>操作人 *</span><input className="input" required disabled={!!busy} value={actor} onChange={e=>setActor(e.target.value)}/></label>}
      {error&&<p className="error" role="alert">{error}</p>}
      {!items.length?<div className="empty compact">暂无已删除记录</div>:<ul className="deleted-record-list">{items.map(item=><li key={item.id}>
        <div><strong>{recordName(item.kind,item.record,state)}</strong><small>{labels[item.kind]}{item.entries.length?` · 含 ${item.entries.length} 条申报`:''} · {item.actor} · {new Date(item.at).toLocaleString('zh-CN')}</small></div>
        <button className="btn btn-sm" disabled={!!busy} aria-label={`恢复${labels[item.kind]}${item.record.name||item.record.id}`} onClick={()=>restore(item.id)}>{busy===item.id?'恢复中…':'恢复'}</button>
      </li>)}</ul>}
    </div><footer><button className="btn" disabled={!!busy} onClick={onClose}>关闭</button></footer>
  </Modal>;
}
