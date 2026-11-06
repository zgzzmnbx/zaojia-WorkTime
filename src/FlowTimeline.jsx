import React,{useEffect,useRef,useState} from 'react';
import {ReactFlow,Handle,Position,Controls,ViewportPortal,useUpdateNodeInternals} from '@xyflow/react';
import {Info,Play,ArrowLeft,ArrowRight,CaretDown,ArrowsOutSimple} from '@phosphor-icons/react';
import '@xyflow/react/dist/style.css';
import CapacityGauge from './CapacityGauge.jsx';
import {entryNumbers,entryDensity,windowContributions,riskLabels,orderedWindows,capacityComparison,riskExplanation,capacityExplanation} from './timelineRisk.js';
import './flow-timeline.css';

const DAY=86400000,day=s=>Date.parse(s+'T00:00:00Z')/DAY;
const iso=n=>new Date(n*DAY).toISOString().slice(0,10);
const date=s=>s?.slice(5).replace('-','/')||'—';
const num=v=>v==null?'—':Number(v).toLocaleString('zh-CN',{maximumFractionDigits:2});
const densityNum=v=>v>0&&v<.01?v.toLocaleString('zh-CN',{maximumSignificantDigits:2}):num(v);
const key=w=>`${w.start}/${w.end}`;

function ClaimNode({data:d}){
  return <div className={`flow-claim ${d.included?'included':'excluded'} ${d.highlighted?'linked':''}`} data-entry-id={d.entry.id}>
    <button className={`claim-button nodrag ${d.density?'has-density':''}`} data-density={d.density?.perDay} style={d.density?{'--density-tint':`${4+24*(d.density.perDay/(.5+d.density.perDay))}%`}:undefined} aria-label={`查看${d.name}申报轨迹`} title={`${d.name} · ${d.entry.start}—${d.entry.end} · ${num(d.entry.amount)}${d.entry.unit}\n${d.densityText}`} onClick={()=>d.onSelect(d.entry.id)} onMouseEnter={()=>d.onHighlight(d.entry.id)} onMouseLeave={()=>d.onHighlight(null)} onFocus={()=>d.onHighlight(d.entry.id)} onBlur={()=>d.onHighlight(null)}>
      <span className="claim-number">{d.number}</span><span className="flow-claim-dates">{date(d.entry.start)} — {date(d.entry.end)}</span><strong>{num(d.entry.amount)}<small>{d.entry.unit}</small></strong>
      {d.density?.perDay>0&&<span className="claim-density-strip" aria-hidden="true" style={{'--density-spacing':`${Math.max(8,Math.min(36,12/d.density.perDay))}px`}}/>}
    </button>
    <Handle type="source" position={Position.Right} isConnectable={false} className={d.included?'':'unused-handle'}/>
  </div>;
}

function LabelNode({data:d}){
  return <button className={`flow-project-label nodrag ${d.included?'included':''}`} onClick={()=>d.onSelect(d.entry.id)} aria-label={`查看项目${d.name}`} title={`${d.name}\n${d.densityText}`}>
    <strong>{d.name}</strong><span>{num(d.entry.amount)} {d.entry.unit}<small>{d.included?'计入本次':'未计入'}</small></span>
    <span className="claim-density-label">{d.density?`均 ${densityNum(d.density.perDay)} 工日/日历天`:'密度待补'}</span>
  </button>;
}

function RangeNode({data:d}){
  return <div className={`flow-range-row ${d.current?'current':''}`} data-window={key(d.window)}>
    <button className="flow-range-label nodrag" onClick={()=>d.onSelect(d.window)}><span>{date(d.window.start)}—{date(d.window.end)}</span><small>{d.window.entry_ids.length} 条累计{d.current?' · 当前':''}</small></button>
    <button className="flow-range nodrag" aria-pressed={d.current} aria-label={`选择${d.window.start}至${d.window.end}${d.window.label}范围`} style={{left:d.left,width:d.width}} onClick={()=>d.onSelect(d.window)} title="各时段独立计算，结果不能相加">
      {d.current&&<span className="flow-range-endpoints" aria-hidden="true"><span>{date(d.window.start)}</span><span className="endpoint-separator">—</span><span>{date(d.window.end)}</span></span>}
      <span className="flow-range-line" aria-hidden="true"/>
      <span className="flow-range-summary"><span className="flow-sigma" aria-hidden="true">Σ</span><b>{num(d.window.demand)}<small> 工日</small></b><span className={`badge badge-sm flow-risk rank-${d.window.rank}`}>{riskLabels[d.window.rank]}</span></span>
    </button>
  </div>;
}

function ResultNode({id,data:d}){
  const ref=useRef(null);
  const updateNodeInternals=useUpdateNodeInternals();
  const known=d.scope;
  const rows=windowContributions(known,d.entries,d.rules);
  const converted=rows.some(e=>e.unit!=='工日');
  const rowUnits=rows.map(e=>`${e.id}:${e.unit}`).join('|');
  const comparison=capacityComparison(known,d.rules);
  const range=d.scope;
  useEffect(()=>{const observer=new ResizeObserver(([e])=>d.onHeight(e.borderBoxSize?.[0]?.blockSize||e.contentRect.height));observer.observe(ref.current);return()=>observer.disconnect();},[d.onHeight]);
  useEffect(()=>{updateNodeInternals(id);},[id,updateNodeInternals,range?.start,range?.end,rowUnits]);
  return <aside ref={ref} className="card bg-base-100 flow-result nodrag nopan" aria-label="相连申报的累计计算">
    <div className="flow-result-caption"><span>本次累计</span><span className="badge badge-sm badge-ghost">模拟</span><button className="btn btn-ghost btn-xs btn-square" aria-label="查看本次计算依据" title={riskExplanation(known,d.rules)||capacityExplanation(known,d.rules)} onClick={()=>d.onRisk(known)}><Info size={16}/></button></div>
    <div className="flow-result-date">{date(range?.start)} — {date(range?.end)}</div>
    <div className="flow-terms">{rows.map(e=><div className="flow-term-wrap" key={e.id}>
      <Handle type="target" id={e.id} position={Position.Left} isConnectable={false} style={{top:'50%',left:-13}}/>
      <button className={`flow-term ${e.unit!=='工日'?'converted':''} ${d.highlightedId===e.id?'linked':''}`} data-entry-id={e.id} onClick={()=>d.onSelect(e.id)} onMouseEnter={()=>d.onHighlight(e.id)} onMouseLeave={()=>d.onHighlight(null)} onFocus={()=>d.onHighlight(e.id)} onBlur={()=>d.onHighlight(null)} title={`${d.projects.find(p=>p.id===e.project_id)?.name} · ${e.start}—${e.end}`}>
        <span className="claim-number">{d.numbers.get(e.id)}</span><span className="flow-term-name">{d.projects.find(p=>p.id===e.project_id)?.name}</span>
        {e.unit==='工日'?<b>{num(e.days)}<small> 工日</small></b>:<span className="flow-conversion"><span>{num(e.amount)} {e.unit}{e.days!=null?` ${e.unit==='工时'?'÷':'×'} ${num(e.unit==='工时'?d.rules.hours_per_day:d.rules.days_per_month)} = `:' · '}</span><b>{e.days!=null?<>{num(e.days)}<small> 工日</small></>:'换算待补'}</b></span>}
      </button>
    </div>)}</div>
      {converted&&<div className="flow-conversion-basis">{rows.some(e=>e.unit==='工时')&&<span>1 工日 = {num(d.rules.hours_per_day)} 工时</span>}{rows.some(e=>e.unit==='人月')&&<span>1 人月 = {num(d.rules.days_per_month)} 工日</span>}</div>}
      <button className="flow-total" onClick={d.onTotal} aria-label={`高亮整段累计${num(known.demand)}工日的全部来源`}><span>{converted?'折合合计':'合计'}</span><strong>{num(known.demand)}<small>工日</small></strong></button>
      <div className="flow-comparison" role="status"><span className={`badge badge-sm flow-risk rank-${known.rank}`}>{riskLabels[known.rank]}</span><span>{comparison?.exceeded?`超出 ${comparison.excess>0&&comparison.excess<.01?comparison.excess.toPrecision(2):num(comparison.excess)} 工日`:'未超出参考线'}</span></div>
      {comparison&&<p className="flow-reference-copy">{comparison.boundary} {num(comparison.threshold)} 工日{d.rules.tolerance>0?'（含容差）':''}</p>}
    <CapacityGauge window={known} rules={d.rules} hideCaption vertical compact/>
  </aside>;
}

const nodeTypes={claim:ClaimNode,label:LabelNode,range:RangeNode,result:ResultNode};

export default function FlowTimeline(props){
  const {entries,projects,windows,scope,selectScope,walking,walkIndex,walkCount,startWalk,stepWalk,exitWalk,rules,onRisk,selectedId,onSelect,onOverlap,heading}=props;
  const hostRef=useRef(null),instanceRef=useRef(null);
  const [width,setWidth]=useState(1000),[showAll,setShowAll]=useState(false),[highlightedId,setHighlightedId]=useState(null);
  const [zoom,setZoom]=useState(1),[resultHeight,setResultHeight]=useState(530);
  useEffect(()=>{const observer=new ResizeObserver(([e])=>setWidth(e.contentRect.width));if(hostRef.current)observer.observe(hostRef.current);return()=>observer.disconnect();},[]);
  useEffect(()=>setHighlightedId(null),[scope?.start,scope?.end]);
  const complete=entries.filter(e=>e.start&&e.end&&!['withdrawn','returned'].includes(e.status)&&e.duplicate!=='duplicate');
  const totalWidth=Math.max(width,820),baseZoom=Math.min(1,width/820),left=154,resultWidth=228,resultX=totalWidth-resultWidth-14,timeWidth=resultX-left-68;
  useEffect(()=>{instanceRef.current?.setViewport({x:0,y:0,zoom:baseZoom});setZoom(baseZoom);},[baseZoom]);
  const numbers=entryNumbers(entries);
  const included=new Set(scope?.entry_ids||[]);
  const sorted=orderedWindows(windows),isCurrent=w=>key(w)===key(scope||{});
  const hidden=sorted.filter(w=>w.rank===0&&!isCurrent(w));
  const shown=walking?(scope?[scope]:[]):sorted.filter(w=>showAll||w.rank>0||isCurrent(w));
  const start=complete.length?Math.min(...complete.map(e=>day(e.start)))-3:0,end=complete.length?Math.max(...complete.map(e=>day(e.end)))+4:28,span=Math.max(28,end-start+1);
  const x=n=>left+(n-start)/span*timeWidth;
  const top=64,rowHeight=70,rangeRowHeight=48;
  const projectBottom=top+complete.length*rowHeight-8,reviewTop=projectBottom+20,rangeTop=reviewTop+30;
  const rangesEnd=rangeTop+shown.length*rangeRowHeight;
  const auxiliaryY=rangesEnd+(hidden.length&&!walking?34:10);
  const range=scope;
  const selectedRangeIndex=shown.findIndex(isCurrent);
  const guideBottom=rangeTop+Math.max(0,selectedRangeIndex)*rangeRowHeight+40;
  const height=Math.max(460,auxiliaryY+48,24+resultHeight+18);
  const highlightTotal=()=>{setHighlightedId(null);if(scope&&!walking)selectScope(scope);};
  const nodes=[];
  complete.forEach((entry,i)=>{
    const density=entryDensity(entry,rules),densityText=density?`平均密度：${num(density.days)} 工日 ÷ ${density.calendarDays} 个日历天 = ${densityNum(density.perDay)} 工日/天。整条蓝色越深、底部刻纹越密，平均投入越高；底部刻纹仅作疏密示意，不代表实际逐日投入。`:'日期、数量或单位折算依据不足，无法计算平均密度。';
    const name=projects.find(p=>p.id===entry.project_id)?.name||'项目待补',data={entry,name,density,densityText,number:numbers.get(entry.id),included:included.has(entry.id),highlighted:highlightedId===entry.id||selectedId===entry.id,onSelect,onHighlight:setHighlightedId};
    nodes.push({id:`label-${entry.id}`,type:'label',position:{x:16,y:top+i*rowHeight},data,style:{width:left-26,height:58},selectable:false,focusable:false});
    nodes.push({id:`claim-${entry.id}`,type:'claim',position:{x:x(day(entry.start)),y:top+i*rowHeight+5},data,style:{width:Math.max(3,(day(entry.end)-day(entry.start)+1)/span*timeWidth),height:42},selectable:false,focusable:false});
  });
  shown.forEach((w,i)=>nodes.push({id:`range-${key(w)}`,type:'range',position:{x:0,y:rangeTop+i*rangeRowHeight},data:{window:w,current:isCurrent(w),onSelect:selectScope,left:x(day(w.start)),width:(day(w.end)-day(w.start)+1)/span*timeWidth},style:{width:resultX-20,height:rangeRowHeight},selectable:false,focusable:false}));
  if(range)nodes.push({id:'calculation',type:'result',position:{x:resultX,y:24},data:{scope,entries,projects,rules,numbers,onSelect,onRisk,onHighlight:setHighlightedId,highlightedId,onTotal:highlightTotal,onHeight:setResultHeight},style:{width:resultWidth},selectable:false,focusable:false});
  // Known dimensions keep controlled nodes visible while hover data changes.
  nodes.forEach(node=>{node.initialWidth=node.style.width;node.initialHeight=node.style.height||resultHeight;});
  const edges=complete.filter(e=>included.has(e.id)).map(e=>({id:`sum-${e.id}`,source:`claim-${e.id}`,target:'calculation',targetHandle:e.id,type:'smoothstep',pathOptions:{borderRadius:12,offset:16},style:{stroke:'var(--accent)',strokeWidth:highlightedId===e.id?2.2:1.2,opacity:highlightedId && highlightedId!==e.id ? .18 : .65},selectable:false,focusable:false}));
  const ticks=Array.from({length:6},(_,i)=>Math.round(start+(span-1)*i/5));
  const reset=()=>{instanceRef.current?.setViewport({x:0,y:0,zoom:baseZoom},{duration:160});setZoom(baseZoom);};
  return <section className="hours-timeline flow-timeline" data-context="total" data-walking={walking} data-step={walking?walkIndex+1:undefined} aria-label="跨项目工时泳道图">
    <div className="chart-toolbar">{heading}<div className="chart-actions">
      {walking?<div className="join walk-controls"><span className="badge badge-soft badge-primary walk-step">{walkIndex+1} / {walkCount}</span><button className="btn btn-sm join-item" aria-label="演示上一步" disabled={walkIndex<=0} onClick={()=>stepWalk(-1)}><ArrowLeft size={15}/></button><button className="btn btn-sm btn-primary join-item" aria-label="演示下一步" disabled={walkIndex>=walkCount-1} onClick={()=>stepWalk(1)}>下一步<ArrowRight size={15}/></button><button className="btn btn-ghost btn-sm" aria-label="从第一步重新演示" onClick={startWalk}>重来</button><button className="btn btn-ghost btn-sm" aria-label="退出逐步演示" onClick={exitWalk}>退出</button></div>:<button className="btn btn-soft btn-primary btn-sm" disabled={!walkCount} onClick={startWalk}><Play size={14}/>逐步演示</button>}
      <button className="btn btn-ghost btn-sm" aria-label="适合窗口" onClick={reset}><ArrowsOutSimple size={17}/><span>适合窗口</span></button><button className="btn btn-ghost btn-square btn-sm" aria-label="查看轨迹图说明" onClick={()=>onOverlap(null)}><Info size={17}/></button>
    </div></div>
    <div className="flow-host" ref={hostRef} style={{height:Math.ceil(height*baseZoom)}}>
    {!complete.length?<div className="empty"><h3>补充投入日期后显示轨迹</h3><p>缺少日期的申报仍保留在下方记录中。</p></div>:<ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} deleteKeyCode={null} panOnDrag={zoom>baseZoom+.001} panActivationKeyCode={null} panOnScroll={false} translateExtent={[[0,0],[totalWidth,height]]} zoomOnScroll={false} zoomOnPinch zoomOnDoubleClick={false} minZoom={baseZoom} maxZoom={1.8} defaultViewport={{x:0,y:0,zoom:baseZoom}} onInit={i=>{instanceRef.current=i;i.setViewport({x:0,y:0,zoom:baseZoom});}} onMove={(_,v)=>setZoom(v.zoom)} onMoveEnd={(_,v)=>{if(v.zoom<=baseZoom+.001&&(Math.abs(v.x)>.01||Math.abs(v.y)>.01))instanceRef.current?.setViewport({x:0,y:0,zoom:baseZoom});}} preventScrolling={false} ariaLabelConfig={{'controls.zoomIn.ariaLabel':'放大画布','controls.zoomOut.ariaLabel':'缩小画布','controls.fitView.ariaLabel':'适应全部节点'}} aria-label="可缩放的工时核查画布">
      <Controls position="bottom-left" showInteractive={false} fitViewOptions={{padding:.04,maxZoom:baseZoom}} aria-label="画布缩放控制"/>
      <ViewportPortal>
        <div className="flow-sheet" style={{width:resultX-20,height:projectBottom}}>
          <h3 className="flow-sheet-label flow-section-title">项目投入</h3>{ticks.map((t,i)=><React.Fragment key={t}><span className="flow-date-tick" style={{left:x(t),transform:i===0?'none':i===ticks.length-1?'translateX(-100%)':'translateX(-50%)'}}>{date(iso(t))}</span><i className="flow-grid-line" style={{left:x(t),top:45,height:projectBottom-45}} aria-hidden="true"/></React.Fragment>)}
          {complete.map((e,i)=><div className="flow-lane-ground" key={e.id} style={{top:top+i*rowHeight-8,height:rowHeight}}/>)}
        </div>
        {range&&<div className="flow-guide-area" data-start={range.start} data-end={range.end} style={{left:x(day(range.start)),top:43,width:(day(range.end)-day(range.start)+1)/span*timeWidth,height:guideBottom-43}} aria-hidden="true"/>}
        {shown.length>0&&<div className="flow-review-ground" style={{top:reviewTop,width:resultX-32,height:rangesEnd-reviewTop+(hidden.length&&!walking?32:4)}}><h3 className="flow-section-title">累计核查</h3></div>}
        {hidden.length>0&&!walking&&<button className="flow-fold nodrag nopan" aria-expanded={showAll} style={{top:rangesEnd+2,left:24}} onClick={()=>setShowAll(v=>!v)}><CaretDown size={12} style={{transform:showAll?'rotate(180deg)':''}}/>{showAll?'收起常规时段':`其余 ${hidden.length} 个常规时段`}</button>}
      </ViewportPortal>
    </ReactFlow>}
    {complete.length>0&&<span className="flow-zoom-value" aria-live="polite">{Math.round(zoom*100)}%</span>}
    </div>
  </section>;
}
