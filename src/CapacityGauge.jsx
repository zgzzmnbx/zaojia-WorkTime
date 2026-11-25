import React, {useEffect,useId,useRef,useState} from 'react';
import {capacityScale} from './timelineRisk.js';

const format=value=>Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2});
const referenceLabel=names=>names.map(name=>/参考$|上限$/.test(name)?name:`${name}参考`).join(' / ');

export default function CapacityGauge({window,rules,label='整段累计',hideCaption=false,vertical=false,compact=false}) {
  const ref=useRef(null),[width,setWidth]=useState(600);
  const bandId=useId();
  useEffect(()=>{
    const observer=new ResizeObserver(([entry])=>setWidth(entry.contentRect.width));
    if(ref.current)observer.observe(ref.current);
    return ()=>observer.disconnect();
  },[]);
  const scale=capacityScale(window,rules);
  if(!scale)return null;
  const inset=16,plotWidth=Math.max(width-2*inset,1),x=value=>inset+value/scale.max*plotWidth;
  const labels=scale.markers.map(marker=>({...marker,x:x(marker.value)}));
  // Keep the scale proportional; only move text, connected back to its exact tick.
  const gap=Math.min(labels.some(label=>label.names.length>1)?136:92,plotWidth/labels.length),edge=gap/2;
  labels.forEach((label,i)=>label.textX=Math.max(inset+edge,label.x,i?labels[i-1].textX+gap:0));
  for(let i=labels.length-1;i>=0;i--)labels[i].textX=Math.min(labels[i].textX,i<labels.length-1?labels[i+1].textX-gap:width-inset-edge);
  const shift=Math.max(labels.at(-1).textX-(width-inset-edge),Math.min(labels[0].textX-inset-edge,labels.reduce((sum,label)=>sum+label.textX-label.x,0)/labels.length));
  labels.forEach(label=>label.textX-=shift);
  const currentX=x(scale.demand),currentLabelX=Math.min(Math.max(currentX,64),width-64);
  const unknown=scale.demand===null;
  const description=`${window.start}至${window.end}，模拟工日参考：${scale.markers.map(m=>m.names.join('、')+format(m.value)).join('，')}；${unknown?'本段工时待补，超出量待核':label+format(scale.demand)+'工日'}${scale.tolerance?`，参考值均含${format(scale.tolerance)}工日容差`:''}${window.missing_calendar?.length?'；日历未维护，参考值为估算':''}`;
  const stops=[0,...scale.values,scale.max];
  if(vertical){
    const axis=68,top=compact?12:22,bottom=compact?174:260,y=value=>bottom-value/scale.max*(bottom-top);
    const refs=[...scale.markers].reverse().map(m=>({...m,y:y(m.value)}));
    refs.forEach((m,i)=>m.labelY=Math.max(top+6,m.y,i?refs[i-1].labelY+38:top+6));
    for(let i=refs.length-1;i>=0;i--)refs[i].labelY=Math.min(refs[i].labelY,i<refs.length-1?refs[i+1].labelY-38:bottom-12-(refs[i].names.length-1)*12);
    const cy=y(scale.demand);
    return <figure ref={ref} className={`capacity-gauge capacity-vertical rank-${window.rank}`} aria-label={description}>
      {unknown&&<div className="capacity-pending">本段工时待补 · 超出量待核</div>}
      <svg width="100%" height={bottom+24} viewBox={`0 0 202 ${bottom+24}`} role="img" aria-label={description}>
        <defs><clipPath id={bandId}><rect x={axis-7} y={top} width="14" height={bottom-top} rx="7"/></clipPath></defs>
        <g clipPath={`url(#${bandId})`}>
          {stops.slice(0,-1).map((start,i)=><rect key={i} className={`capacity-zone rank-${i}`} x={axis-7} y={y(stops[i+1])} width="14" height={Math.max(0,y(start)-y(stops[i+1]))}/>)}
        </g>
        <text className="capacity-zero" x={axis} y={bottom+17} textAnchor="middle">0</text>
        {refs.map((m,i)=><g className="capacity-reference" data-value={m.value} key={i}>
          <title>{referenceLabel(m.names)}：{format(m.value)}工日</title>
          <line x1={axis-7} x2={axis+7} y1={m.y} y2={m.y}/>
          <path className="capacity-leader" d={`M ${axis+7} ${m.y} C ${axis+20} ${m.y}, ${axis+22} ${m.labelY}, ${axis+32} ${m.labelY}`}/>
          <text x={axis+38} y={m.labelY-3}>{m.names.map((name,index)=><tspan key={name} x={axis+38} dy={index?12:0}>{name}</tspan>)}</text>
          <text className="capacity-reference-value" x={axis+38} y={m.labelY+13+(m.names.length-1)*12}>{format(m.value)}</text>
        </g>)}
        {!unknown&&<g className="capacity-current" data-value={scale.demand}>
          <title>{label} {format(scale.demand)}工日</title>
          <rect className="capacity-current-pill" x="0" y={cy-18} width="49" height="36" rx="7"/>
          <text className="capacity-current-caption" x="24.5" y={cy-4} textAnchor="middle">当前</text>
          <text className="capacity-current-number" x="24.5" y={cy+11} textAnchor="middle" fontSize={format(scale.demand).length>6?10:13}>{format(scale.demand)}</text>
          <line x1="49" x2={axis-6} y1={cy} y2={cy}/>
          <circle className="capacity-current-dot" cx={axis} cy={cy} r="5"/>
        </g>}
      </svg>
      {window.missing_calendar?.length>0&&<figcaption className="fine">{window.missing_calendar.join('、')}年日历未维护，参考值按工作日估算。</figcaption>}
    </figure>;
  }
  return <figure ref={ref} className={`capacity-gauge rank-${window.rank}`} aria-label={description}>
    <svg width="100%" height="104" role="img" aria-label={description}>
      {!hideCaption&&<text className="capacity-caption" x="0" y="13">{window.start}—{window.end} · 工日 · 模拟{scale.tolerance>0?`（参考值含${format(scale.tolerance)}容差）`:''}</text>}
      {stops.slice(0,-1).map((start,i)=><rect key={i} className={`capacity-zone rank-${i}`} x={x(start)} y="42" width={Math.max(0,x(stops[i+1])-x(start))} height="7"/>)}
      <text className="capacity-zero" x={inset} y="65" textAnchor="middle">0</text>
      {labels.map((marker,i)=><g key={i} className="capacity-reference" data-value={marker.value}>
        <title>{referenceLabel(marker.names)}：{format(marker.value)}工日{scale.tolerance?`（原值${format(marker.raw)}＋容差${format(scale.tolerance)}）`:''}</title>
        <line x1={x(marker.value)} x2={x(marker.value)} y1="37" y2="54"/>
        <path className="capacity-leader" d={`M ${x(marker.value)} 54 L ${marker.textX} 65`}/>
        <text x={marker.textX} y="80" textAnchor="middle">{marker.names.join(' / ')}</text>
        <text className="capacity-reference-value" x={marker.textX} y="97" textAnchor="middle">{format(marker.value)}</text>
      </g>)}
      {unknown?<text className="capacity-caption capacity-pending" x={width-inset} y="32" textAnchor="end">本段工时待补 · 超出量待核</text>:<g className="capacity-current" data-value={scale.demand}>
        <title>{label}申报 {format(scale.demand)} 工日</title>
        <text x={currentLabelX} y="32" textAnchor="middle">{label} {format(scale.demand)}</text>
        <path d={`M ${currentX} 36 L ${currentX-4} 41 L ${currentX} 46 L ${currentX+4} 41 Z`}/>
        <line x1={currentX} x2={currentX} y1="42" y2="53"/>
      </g>}
    </svg>
    {window.missing_calendar?.length>0&&<figcaption className="fine">{window.missing_calendar.join('、')}年日历未维护，参考值按工作日估算。</figcaption>}
  </figure>;
}
