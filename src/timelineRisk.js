// Colors describe capacity screening windows, never observed daily workload.
import {unitLabel} from './units.js';
export const riskLabels = ['低风险', '中风险', '高风险', '极高风险'];
const amount = value => Number(value).toLocaleString('zh-CN', {maximumFractionDigits: Math.abs(value)>0&&Math.abs(value)<0.01?6:2});
const dateLabel = value => {const [y,m,d]=value.split('-').map(Number);return `${y}年${m}月${d}日`;};

export const orderedWindows = windows => [...windows].sort((a,b)=>a.start.localeCompare(b.start)||a.end.localeCompare(b.end));
export const entryNumbers = entries => new Map(entries.map((entry,i)=>[entry.id,i+1]));

export function capacityComparison(window, rules = {}) {
  if(!window)return null;
  const rank=window.rank,base=[window.c0,window.c0,window.c1,window.c2][rank];
  const threshold=base+(rules.tolerance??0);
  return {boundary:['工作日参考','工作日参考','含加班上限','最高参考上限'][rank],threshold,excess:rank>0?Math.max(0,window.demand-threshold):0,exceeded:rank>0};
}

// Show the actual assumptions beside the numbers, rather than an unexplained grade.
export function capacityStandards(window, rules = {}) {
  if(!window || ![window.n,window.c0,window.c1,window.c2,window.demand].every(Number.isFinite))return null;
  const tolerance=rules.tolerance??0;
  const comparison=capacityComparison(window,rules);
  const overtime=window.c1-window.c0;
  const rows=[
    {id:'workdays',label:`${amount(window.c0)} 个工作日`,basis:'每天按 1 工日',raw:window.c0},
    {id:'overtime',label:'工作日＋模拟加班',basis:`${amount(window.c0)}＋${amount(overtime)} 工日`,raw:window.c1},
    {id:'calendar',label:`${amount(window.n)} 个日历天`,basis:'含周末，每天按 1 工日',raw:window.n},
  ].map(row=>({...row,value:row.raw+tolerance,exceeded:window.demand>row.raw+tolerance+1e-9}));
  const calendarWins=window.n>=window.c1;
  const basis=window.rank<=1?`${amount(window.c0)}个工作日，每天按1工日`:window.rank===2?
    `工作日${amount(window.c0)}工日＋模拟加班${amount(overtime)}工日`:
    calendarWins?`${amount(window.n)}个日历天，每天按1工日`:`工作日＋模拟加班（${amount(window.c1)}工日，大于${amount(window.n)}个日历天）`;
  const sentence=`本段申报${amount(window.demand)}工日；按${basis}${tolerance?`，再加${amount(tolerance)}工日容差`:''}，参考量为${amount(comparison.threshold)}工日，${comparison.excess>0?`多出${amount(comparison.excess)}工日`:'未超出'}。`;
  const estimated = window.missing_calendar?.length > 0 || (window.basis && window.basis !== '人员投入期');
  const workdayExcess = Math.max(0, window.demand - window.c0 - tolerance);
  const period = window.start && window.end ? `${dateLabel(window.start)}—${dateLabel(window.end)}` : '该核查时段';
  const workdayExplanation = `${period}，计入${window.entry_ids?.length ?? 0}条完整申报，合计${amount(window.demand)}工日。按当前${estimated?'暂估':''}日历有${amount(window.c0)}个工作日，每天按1工日比较${tolerance?`，另计${amount(tolerance)}工日容差`:''}，${workdayExcess > 1e-9?`超出工作日基准${amount(workdayExcess)}工日`:'未超出工作日基准'}。${window.missing_calendar?.length?`${window.missing_calendar.join('、')}年放假调休安排待补。`:''}`;
  return {rows,comparison,basis,sentence,tolerance,bands:{green:window.c0+tolerance,yellow:window.c1+tolerance,red:window.c2+tolerance},
    workdayExplanation,
    equation:comparison.excess>0?`申报 ${amount(window.demand)} − 参考 ${amount(comparison.threshold)} ＝ 多出 ${amount(comparison.excess)} 工日`:`申报 ${amount(window.demand)} ≤ 参考 ${amount(comparison.threshold)} 工日`,
    compact:`申报${amount(window.demand)}工日 / 工作日${estimated?'约':''}${amount(window.c0)}天`};
}

export function windowContributions(window, entries, rules = {}) {
  return [...new Set(window?.entry_ids??[])].flatMap(id=>{
    const entry=entries.find(e=>e.id===id);
    if(!entry)return [];
    const days=entry.unit==='工日'?entry.amount:entry.unit==='工时'&&rules.hours_per_day>0?entry.amount/rules.hours_per_day:null;
    return [{...entry,days}];
  });
}

export function capacityScale(window, rules = {}) {
  if(!window || ![window.c0,window.c1,window.c2].every(v=>Number.isFinite(v)&&v>=0))return null;
  if(window.demand!==null&&(!Number.isFinite(window.demand)||window.demand<0))return null;
  const tolerance=rules.tolerance??0;
  const values=[window.c0,window.c1,window.c2].map(v=>v+tolerance);
  const names=['工作日','含加班上限','最高参考上限'];
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
  const reference=['按工作日数、每天1工日计算，参考量为','计入参考加班量后，模拟参考量为',`比较日历天数${amount(window.n)}与含加班上限${amount(window.c1)}工日，最高参考上限为`][window.rank-1];
  const excess=window.demand-threshold-tolerance;
  // Use the actual crossed boundary, not window.excess (rank 2's excess is 0).
  if(excess<=0)return '';
  return `${dateLabel(window.start)}—${dateLabel(window.end)}，${count}个项目合计申报${amount(window.demand)}工日；${reference}${amount(threshold)}工日${tolerance>0?`，再计入${amount(tolerance)}工日容差后`:''}，仍多出${amount(excess)}工日，因此提示“${riskLabels[window.rank]}”。`;
}

export function capacityExplanation(window, rules = {}) {
  if(!window)return '';
  const overtime=window.c1-window.c0;
  const overtimeBasis=rules.hours_per_day>0&&rules.average_month>0?`（${amount(rules.overtime_hours)}工时/月 ÷ ${amount(rules.hours_per_day)}工时/工日 × ${window.n}天 ÷ ${amount(rules.average_month)}天/月）`:'';
  return `这段时间共${window.n}个日历天，按当前日历有${amount(window.c0)}个工作日，每天以1工日作筛查参考；再加模拟加班${amount(overtime)}工日${overtimeBasis}，含加班上限为${amount(window.c1)}工日。另按全部${window.n}个日历天、每天1工日得到${window.n}工日；取日历天数与含加班上限中的较大值，最高参考上限为${amount(window.c2)}工日${rules.tolerance>0?`，另加${amount(rules.tolerance)}工日容差`:''}。这些是总量筛查假设，不是实际逐日投入。`;
}

export function windowReason(window, entries, projects, rules = {}) {
  if(!window)return '';
  const rows=windowContributions(window,entries,rules);
  const sources=rows.map(e=>`${projects.find(p=>p.id===e.project_id)?.name||'项目待补'}（${e.start||'日期待补'}至${e.end||'日期待补'}，${amount(e.amount)}${unitLabel(e.unit)}）`).join('、');
  return `${sources}。${riskExplanation(window,rules)||`该时段合计${amount(window.demand)}工日，未超过工作日参考量。`}请核对这些完整申报的数量、投入日期和加班依据；仅凭期间交叉无法确定哪条申报重复或应审减多少。`;
}
const day = value => Date.parse(`${value}T00:00:00Z`) / 86400000;

// An interval average for visual comparison only; never allocate it to daily records.
export function entryDensity(entry, rules = {}) {
  const validDate=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(day(value))&&new Date(day(value)*86400000).toISOString().slice(0,10)===value;
  if(!validDate(entry?.start)||!validDate(entry?.end)||entry.end<entry.start||!Number.isFinite(entry.amount)||entry.amount<0)return null;
  const days=windowContributions({entry_ids:[entry.id]},[entry],rules)[0]?.days;
  if(!Number.isFinite(days)||days<0)return null;
  const calendarDays=day(entry.end)-day(entry.start)+1;
  return {days,calendarDays,perDay:days/calendarDays};
}

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
