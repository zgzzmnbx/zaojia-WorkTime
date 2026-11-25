import React, {useState} from 'react';
import {recordId} from './recordId.js';

export const levels=['技术专家','项目经理','高级技术人员','一般技术人员'];
const imageTypes=['image/jpeg','image/png','image/webp'];

export const newPersonProfile=()=>({company:'',title_permanent:true,qualification_required:true});
export const personLabel=p=>[p.name,p.code,p.company].filter(Boolean).join(' · ');

export function CertificatePreview({person,api}){
  if(!person.certificate_id)return null;
  const source=person._certificate?`data:${person._certificate.mime};base64,${person._certificate.data}`:`${api}/certificate/${encodeURIComponent(person.certificate_id)}`;
  return <details className="certificate-preview"><summary>查看资格证</summary><img src={source} alt={`${person.name||'人员'}的资格证`} loading="lazy"/></details>;
}

export function CertificateInput({onChange,required=false,label='资格证图片',onReading}){
  const [error,setError]=useState('');
  async function chooseCertificate(file){
    if(!file)return;
    setError('');
    if(!imageTypes.includes(file.type)||file.size>3_000_000){setError('请选择 3 MB 以内的 JPG、PNG 或 WebP 图片');return;}
    onReading?.(1);
    try{
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
      const id=recordId();
      onChange({certificate_id:id,_certificate:{id,mime:file.type,name:file.name,data}});
    }catch{setError('无法读取图片，请重新选择');}
    finally{onReading?.(-1);}
  }
  return <><input className="file-input" type="file" aria-label={label} accept="image/jpeg,image/png,image/webp" required={required} onChange={e=>chooseCertificate(e.target.files[0])}/>{error&&<p className="error" role="alert">{error}</p>}</>;
}

export function PersonFields({person,onChange,api}){
  const permanent=person.title_permanent===true;
  const required=person.qualification_required===true;
  return <>
    <div className="form-grid person-identity">
      <label className="field"><span>姓名 *</span><input className="input" value={person.name??''} onChange={e=>onChange({name:e.target.value})} required/></label>
      <label className="field"><span>工号 *</span><input className="input" value={person.code??''} onChange={e=>onChange({code:e.target.value})} required/></label>
      <label className="field"><span>所属单位 *</span><input className="input" value={person.company??''} onChange={e=>onChange({company:e.target.value})} required/></label>
      <label className="field"><span>职称（级别）{required?' *':''}</span><select className="select" value={person.title??''} onChange={e=>onChange({title:e.target.value})} required={required}>
        <option value="">请选择级别</option>{levels.map(level=><option key={level}>{level}</option>)}
        {person.title&&!levels.includes(person.title)&&<option value={person.title}>{person.title}（原有记录）</option>}
      </select></label>
    </div>
    <div className="certificate-fields">
      <label className="field"><span>资格证图片{required&&!person.certificate_id?' *':''}</span><CertificateInput required={required&&!person.certificate_id} onChange={onChange}/></label>
      <label className="checkline"><input className="checkbox checkbox-sm" type="checkbox" checked={permanent} onChange={e=>onChange({title_permanent:e.target.checked,...(e.target.checked?{title_from:'',title_to:''}:{})})}/>长期有效</label>
    </div>
    <CertificatePreview person={person} api={api}/>
    {!permanent&&<div className="form-grid">
      <label className="field"><span>资格证有效起始日期 *</span><input className="input" type="date" value={person.title_from??''} onChange={e=>onChange({title_from:e.target.value})} required/></label>
      <label className="field"><span>资格证有效终止日期 *</span><input className="input" type="date" value={person.title_to??''} onChange={e=>onChange({title_to:e.target.value})} required/></label>
    </div>}
  </>;
}
