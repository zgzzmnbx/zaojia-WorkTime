// Colors describe capacity screening windows, never observed daily workload.
export const riskLabels = ['常规', '轻度', '重点', '高负荷'];
const amount = value => Number(value).toLocaleString('zh-CN', {maximumFractionDigits: Math.abs(value)>0&&Math.abs(value)<0.01?6:2});
const dateLabel = value => {const [y,m,d]=value.split('-').map(Number);return `${y}年${m}月${d}日`;};

export const orderedWindows = windows => [...windows].sort((a,b)=>a.start.localeCompare(b.start)||a.end.localeCompare(b.end));
export const entryNumbers = entries => new Map(entries.map((entry,i)=>[entry.id,i+1]));

export function capacityComparison(window, rules = {}) {
  if(!window)return null;
  const rank=window.rank,base=[window.c0,window.c0,window.c1,window.c2][rank];
  const threshold=base+(rules.tolerance??0);
  return {boundary:['常规参考','常规参考','加班参考','高负荷参考'][rank],threshold,excess:Math.max(0,window.demand-threshold),exceeded:rank>0};
}

export function windowContributions(window, entries, rules = {}) {
  return [...new Set(window?.entry_ids??[])].flatMap(id=>{
    const entry=entries.find(e=>e.id===id);
    if(!entry)return [];
    const days=entry.unit==='工日'?entry.amount:entry.unit==='工时'&&rules.hours_per_day>0?entry.amount/rules.hours_per_day:entry.unit==='人月'&&rules.days_per_month>0?entry.amount*rules.days_per_month:null;
    return [{...entry,days}];
  });
}

export function capacityScale(window, rules = {}) {
  if(!window || ![window.c0,window.c1,window.c2].every(v=>Number.isFinite(v)&&v>=0))return null;
  if(window.demand!==null&&(!Number.isFinite(window.demand)||window.demand<0))return null;
  const tolerance=rules.tolerance??0;
  const values=[window.c0,window.c1,window.c2].map(v=>v+tolerance);
  const names=['常规','加班后','高负荷'];
  const markers=[];
  values.forEach((value,index)=>{
    const previous=markers.at(-1);
    if(previous?.value===value)previous.names.push(names[index]);
    else markers.push({value,names:[names[index]],raw:value-tolerance});
  });
  return {values,markers,demand:window.demand,max:Math.max(1,window.demand,...values)*1.12,tolerance};
}

export function riskExplanation(window, rules = {}) {
  if(!window || window.rank<1)return '';
  const threshold=[window.c0,window.c1,window.c2][window.rank-1];
  const tolerance=rules.tolerance??0;
  if(!Number.isFinite(threshold)||!Number.isFinite(window.demand))return '';
  const count=new Set(window.project_ids).size;
  const reference=['按模拟工作日计算，常规可安排','计入参考加班量后，模拟可安排','按当前模拟口径，高负荷参考量为'][window.rank-1];
  const excess=window.demand-threshold-tolerance;
  // Use the actual crossed boundary, not window.excess (rank 2's excess is 0).
  if(excess<=0)return '';
  return `${dateLabel(window.start)}—${dateLabel(window.end)}，${count}个项目合计申报${amount(window.demand)}工日；${reference}${amount(threshold)}工日${tolerance>0?`，再计入${amount(tolerance)}工日容差后`:''}，仍多出${amount(excess)}工日，因此提示“${window.label}”。`;
}

export function capacityExplanation(window, rules = {}) {
  if(!window)return '';
  const overtime=window.c1-window.c0;
  return `这段时间共${window.n}个日历天，模拟日历中的工作日可安排${amount(window.c0)}工日，加上按当前参数折算的${amount(overtime)}工日参考加班量，得到${amount(window.c1)}工日；高负荷参考量取日历天数与加班后参考量中的较大值，为${amount(window.c2)}工日${rules.tolerance>0?`，比较时另加${amount(rules.tolerance)}工日容差`:''}。`;
}
const day = value => Date.parse(`${value}T00:00:00Z`) / 86400000;

// Reference-only view of an overlap; follows engine.Capacity without allocating claims.
export function overlapCapacity(overlap, rules, calendars = []) {
  if(!overlap||!Number.isInteger(overlap.start)||!Number.isInteger(overlap.end)||overlap.end<overlap.start)return null;
  if(![rules?.hours_per_day,rules?.average_month].every(v=>Number.isFinite(v)&&v>0)||!Number.isFinite(rules?.overtime_hours)||rules.overtime_hours<0)return null;
  const holidays=new Set(calendars.flatMap(c=>c.holidays)),makeup=new Set(calendars.flatMap(c=>c.makeup_days));
  const iso=d=>new Date(d*86400000).toISOString().slice(0,10);
  const start=iso(overlap.start),end=iso(overlap.end),n=overlap.end-overlap.start+1;
  let c0=0;
  for(let d=overlap.start;d<=overlap.end;d++){
    const weekday=new Date(d*86400000).getUTCDay(),date=iso(d);
    if(makeup.has(date)||(!holidays.has(date)&&weekday!==0&&weekday!==6))c0++;
  }
  const c1=c0+rules.overtime_hours/rules.hours_per_day*n/rules.average_month;
  const missing_calendar=[];
  for(let year=Number(start.slice(0,4));year<=Number(end.slice(0,4));year++)if(!calendars.some(c=>c.year===year))missing_calendar.push(year);
  return {start,end,n,c0,c1,c2:Math.max(n,c1),demand:null,rank:'pending',missing_calendar};
}

export function overlapPeriods(entries) {
  const valid=entries.filter(e=>e.start&&e.end&&!['withdrawn','returned'].includes(e.status)&&e.duplicate!=='duplicate');
  const boundaries=[...new Set(valid.flatMap(e=>[day(e.start),day(e.end)+1]))].sort((a,b)=>a-b);
  const result=[];
  for(let i=0;i<boundaries.length-1;i++){
    const active=valid.filter(e=>day(e.start)<=boundaries[i]&&day(e.end)>=boundaries[i]);
    if(new Set(active.map(e=>e.project_id)).size>=2)result.push({start:boundaries[i],end:boundaries[i+1]-1,entries:active});
  }
  return result;
}

export function overlapSlice(entry, overlap) {
  if(!overlap?.entries.some(e=>e.id===entry.id))return null;
  const start=day(entry.start),end=day(entry.end),a=Math.max(start,overlap.start),b=Math.min(end,overlap.end);
  if(a>b)return null;
  return {left:(a-start)/(end-start+1)*100,width:(b-a+1)/(end-start+1)*100};
}

export function exactOverlapWindow(overlap, windows) {
  if(!overlap)return null;
  const ids=new Set(overlap.entries.map(e=>e.id));
  return windows.find(w=>day(w.start)===overlap.start&&day(w.end)===overlap.end&&w.entry_ids.length===ids.size&&w.entry_ids.every(id=>ids.has(id)))??null;
}
const priority = (a,b) => b.rank-a.rank || (b.ratio??0)-(a.ratio??0) ||
  (day(a.end)-day(a.start))-(day(b.end)-day(b.start));

export function entryRisk(id, windows) {
  // Partial temporal intersection is not evidence that a claim caused overload.
  return windows.filter(w=>w.entry_ids.includes(id)).sort(priority)[0] ?? null;
}

export function riskSegments(windows) {
  const sorted=[...windows].sort(priority);
  const boundaries=[...new Set(sorted.flatMap(w=>[day(w.start),day(w.end)+1]))].sort((a,b)=>a-b);
  const segments=[];
  for(let i=0;i<boundaries.length-1;i++){
    const start=boundaries[i],end=boundaries[i+1]-1;
    const window=sorted.find(w=>day(w.start)<=start&&day(w.end)>=end);
    if(!window)continue;
    const last=segments.at(-1);
    if(last?.window===window&&last.end+1===start)last.end=end;
    else segments.push({start,end,window});
  }
  return segments;
}

export function personRisk(result) {
  if(result.worst?.rank>0)return result.worst.rank;
  if(Object.values(result.checks).includes('需核查'))return 'review';
  if(!result.worst||result.pending_count>0)return 'pending';
  return 0;
}
