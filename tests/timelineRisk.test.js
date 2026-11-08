import {execFileSync} from 'node:child_process';
import test from 'node:test';
import assert from 'node:assert/strict';
import { scheduleRisks } from '../src/scheduleRisks.js';
import { entryDensity, entryNumbers, entryRisk, riskSegments, personRisk, riskExplanation, capacityExplanation, capacityScale, windowContributions, overlapPeriods, overlapSlice, exactOverlapWindow, orderedWindows, capacityComparison, overlapCapacity } from '../src/timelineRisk.js';

test('工期风险保留全部独立预警时段，只关联完整计入来源，不复制最紧时段摘要',()=>{
  const a={start:'2026-03-02',end:'2026-04-17',rank:3,entry_ids:['a','b'],c0:30,c1:36,c2:40,demand:50};
  const b={...a,start:'2026-03-16',entry_ids:['b'],demand:45};
  const result={windows:[b,{...a,rank:0,entry_ids:['wide']},a],findings:[{category:'跨项目',level:'warning',message:'最紧时段为高负荷核查，仅作模拟筛查'}],rule_snapshot:{tolerance:1}};
  const rows=scheduleRisks(result);
  assert.deepEqual(rows.map(r=>r.entryIds),[['a','b'],['b']]);
  assert.deepEqual(rows.map(r=>r.comparison.excess),[9,4]);
  assert.equal(rows.length,2);
});
test('工期风险收集单条与人员级事项，待核不冒充超量，保留不同申报的同类问题',()=>{
  const finding={category:'实施期',level:'pending',message:'实际投入日期待补',entry_id:'a'};
  const result={entries:[{id:'a',start:null,end:null}],windows:[],findings:[finding,{...finding},{...finding,entry_id:'b'},{category:'跨项目',level:'pending',message:'日历待维护'},{category:'职称计费',level:'warning',message:'单价不一致'}]};
  const rows=scheduleRisks(result);
  assert.equal(rows.length,3);
  assert.ok(rows.every(r=>r.level==='pending'&&!r.window));
  assert.deepEqual(rows.map(r=>r.entryIds),[['a'],['b'],[]]);
  assert.equal(rows[0].start,null);
});
test('无工期异常与未提供结果分别保持空集；缺窗口时不丢失已有预警摘要',()=>{
  assert.deepEqual(scheduleRisks(null),[]);
  assert.deepEqual(scheduleRisks({windows:[],findings:[]}),[]);
  assert.equal(scheduleRisks({findings:[{category:'跨项目',level:'warning',message:'最紧时段为重点核查'}]}).length,1);
});

test('平均密度包含首尾日，不采用认定量或误作工作日密度',()=>{
  const entry={id:'a',start:'2026-03-02',end:'2026-03-27',unit:'工日',amount:18,recognized_amount:12};
  assert.deepEqual(entryDensity(entry),{days:18,calendarDays:26,perDay:18/26});
  assert.equal(entryDensity({...entry,end:entry.start,amount:2}).perDay,2);
  assert.equal(entryDensity({...entry,amount:0}).perDay,0);
});
test('密度统一折算工日，缺参数或未知单位不显示伪造纹理',()=>{
  const entry={id:'a',start:'2026-03-02',end:'2026-03-03',unit:'工时',amount:16};
  assert.equal(entryDensity(entry,{hours_per_day:8}).perDay,1);
  assert.equal(entryDensity({...entry,unit:'人月',amount:1},{days_per_month:20}).perDay,10);
  for(const rules of [{},{hours_per_day:0},{hours_per_day:-8}])assert.equal(entryDensity(entry,rules),null);
  assert.equal(entryDensity({...entry,unit:'项'}),null);
});
test('缺失、非法或倒置日期及非法数量不生成密度',()=>{
  const entry={id:'a',start:'2026-03-02',end:'2026-03-03',unit:'工日',amount:1};
  for(const patch of [{start:''},{start:'2026-02-30'},{end:'2026-03-01'},{amount:null},{amount:-1},{amount:Infinity}])assert.equal(entryDensity({...entry,...patch}),null);
});

const broad={start:'2026-03-02',end:'2026-04-30',rank:0,entry_ids:['wide','short1','short2','later']};
const red={start:'2026-03-16',end:'2026-03-27',rank:3,entry_ids:['short1','short2']};
test('局部超量不会把仅相交的长期申报染红',()=>{
  assert.equal(entryRisk('wide',[broad,red]).rank,0);
  assert.equal(entryRisk('short1',[broad,red]).rank,3);
  assert.equal(entryRisk('later',[broad,red]).rank,0);
  assert.equal(entryRisk('missing',[broad,red]),null);
});
test('预警带只在局部核查窗口内取高等级，含首尾日',()=>{
  const segments=riskSegments([broad,red]);
  assert.deepEqual(segments.map(s=>s.window.rank),[0,3,0]);
  assert.equal(segments[1].end-segments[1].start+1,12);
  assert.equal(segments[0].end+1,segments[1].start);
  assert.equal(segments[1].end+1,segments[2].start);
});
test('同一时段选择更高预警且与输入顺序无关',()=>{
  const orange={...red,rank:2};
  assert.deepEqual(riskSegments([red,orange]),riskSegments([orange,red]));
  assert.equal(riskSegments([red,orange])[0].window.rank,3);
});
test('正常交叉保持绿色，缺计算结果不冒充正常',()=>{
  assert.equal(riskSegments([broad])[0].window.rank,0);
  assert.deepEqual(riskSegments([]),[]);
});
test('轻度人员不被其他检查的通用警告提升为橙色',()=>{
  assert.equal(personRisk({worst:{rank:1},checks:{'跨项目':'需核查'},pending_count:0}),1);
  assert.equal(personRisk({worst:{rank:0},checks:{'职称计费':'需核查'},pending_count:0}),'review');
  assert.equal(personRisk({worst:null,checks:{},pending_count:1}),'pending');
});

const local={...red,n:12,demand:18,c0:10,c1:11.78,c2:12,project_ids:['p1','p2'],label:'高负荷核查'};
test('局部高负荷解释指明时间、去重项目数和超出高负荷线的数量',()=>{
  const text=riskExplanation({...local,project_ids:['p1','p2','p1']});
  assert.match(text,/2026年3月16日—2026年3月27日/);
  assert.match(text,/2个项目合计申报18工日/);
  assert.match(text,/高负荷参考量为12工日，仍多出6工日/);
  assert.match(text,/因此提示“高负荷核查”/);
});
test('重点核查比较加班参考线，不误用后端的零excess',()=>{
  const text=riskExplanation({...local,rank:2,demand:38,c0:30,c1:35.9210526,c2:40,excess:0,label:'重点核查'});
  assert.match(text,/计入参考加班量后，模拟可安排35.92工日，仍多出2.08工日/);
  assert.match(text,/因此提示“重点核查”/);
});
test('说明遵循容差，不把有效容差说成超量',()=>{
  assert.match(riskExplanation(local,{tolerance:1}),/再计入1工日容差后，仍多出5工日/);
  assert.equal(riskExplanation(local,{tolerance:6}),'');
});
test('正常与缺失结果不生成警告，微小超量不四舍五入成0',()=>{
  assert.equal(riskExplanation(null),'');
  assert.equal(riskExplanation({...local,rank:0}),'');
  assert.match(riskExplanation({...local,demand:12.004}),/多出0.004工日/);
});
test('容量来源说明支持加班参考量高于日历天数的配置',()=>{
  assert.match(capacityExplanation({...local,c1:15,c2:15}),/工作日可安排10工日，加上按当前参数折算的5工日参考加班量/);
  assert.match(capacityExplanation({...local,c1:15,c2:15}),/较大值，为15工日/);
});

test('参考刻度包含当前申报且保留真实比例，超量不截断',()=>{
  const scale=capacityScale(local);
  assert.deepEqual(scale.values,[10,11.78,12]);
  assert.equal(scale.demand,18);
  assert.ok(scale.max>scale.demand);
  assert.equal(scale.values[0]/scale.values[2],10/12);
  assert.ok(capacityScale({...local,demand:18000}).max>18000);
});
test('相同参考线合并标注，容差反映在比较位置',()=>{
  const scale=capacityScale({...local,c1:12},{tolerance:1});
  assert.deepEqual(scale.values,[11,13,13]);
  assert.equal(scale.markers.length,2);
  assert.deepEqual(scale.markers[1],{value:13,names:['加班后','高负荷'],raw:12});
});
test('空值不绘制假刻度，全零仍可展示且合并参考线',()=>{
  assert.equal(capacityScale(null),null);
  assert.equal(capacityScale({...local,c0:null}),null);
  const scale=capacityScale({...local,demand:0,c0:0,c1:0,c2:0});
  assert.ok(scale.max>0);
  assert.equal(scale.markers.length,1);
});

test('合计标签只取核查窗口关联记录，工时和人月统一折算',()=>{
  const entries=[{id:'a',amount:18,unit:'工日',recognized_amount:12},{id:'b',amount:160,unit:'工时'},{id:'c',amount:1,unit:'人月'},{id:'wide',amount:99,unit:'工日'}];
  const rows=windowContributions({entry_ids:['a','b','c','a']},entries,{hours_per_day:8,days_per_month:20});
  assert.deepEqual(rows.map(r=>r.id),['a','b','c']);
  assert.deepEqual(rows.map(r=>r.days),[18,20,20]);
  assert.equal(rows.reduce((sum,r)=>sum+r.days,0),58);
});
test('缺失折算不得伪造工日，空窗口没有合计来源',()=>{
  assert.equal(windowContributions({entry_ids:['a']},[{id:'a',amount:1,unit:'人月'}])[0].days,null);
  assert.deepEqual(windowContributions(null,[]),[]);
});

const claims=[
  {id:'a',project_id:'p1',start:'2026-03-02',end:'2026-03-27',amount:18},
  {id:'b',project_id:'p2',start:'2026-03-16',end:'2026-04-10',amount:20},
  {id:'c',project_id:'p3',start:'2026-03-23',end:'2026-04-17',amount:20},
];
const isoDay=n=>new Date(n*86400000).toISOString().slice(0,10);
test('58工日的三条完整申报与三段期间交叉独立，交叉不分摊数量',()=>{
  const overlaps=overlapPeriods(claims);
  assert.deepEqual(overlaps.map(o=>[isoDay(o.start),isoDay(o.end),o.entries.map(e=>e.id)]),[
    ['2026-03-16','2026-03-22',['a','b']],
    ['2026-03-23','2026-03-27',['a','b','c']],
    ['2026-03-28','2026-04-10',['b','c']],
  ]);
  assert.ok(overlaps.every(o=>!('demand' in o)&&!('hours' in o)));
  const slice=overlapSlice(claims[0],overlaps[0]);
  assert.equal(slice.left,14/26*100);
  assert.equal(slice.width,7/26*100);
  assert.equal(overlapSlice(claims[2],overlaps[0]),null);
});
test('相邻不重叠，共用一天算交叉，同项目及撤销记录不制造跨项目重叠',()=>{
  const first={...claims[0],start:'2026-03-01',end:'2026-03-02'};
  assert.deepEqual(overlapPeriods([first,{...claims[1],start:'2026-03-03',end:'2026-03-04'}]),[]);
  const last={...claims[1],start:'2026-03-02',end:'2026-03-04'};
  assert.equal(overlapPeriods([first,last])[0].end-overlapPeriods([first,last])[0].start,0);
  assert.deepEqual(overlapPeriods([first,{...last,project_id:'p1'}]),[]);
  assert.deepEqual(overlapPeriods([first,{...last,status:'withdrawn'}]),[]);
});

test('部分交叉不能借用包含整条申报的窗口合计',()=>{
  const overlap=overlapPeriods(claims)[0];
  assert.equal(exactOverlapWindow(overlap,[{start:'2026-03-02',end:'2026-04-17',entry_ids:['a','b','c'],demand:58}]),null);
});
test('交叉段与有效窗口日期及全部记录一致时，才展示已知累计',()=>{
  const same=claims.slice(0,2).map(e=>({...e,start:'2026-03-02',end:'2026-03-27'}));
  const overlap=overlapPeriods(same)[0];
  const window={start:'2026-03-02',end:'2026-03-27',entry_ids:['a','b'],demand:38};
  assert.equal(exactOverlapWindow(overlap,[window]),window);
  assert.equal(exactOverlapWindow(overlap,[{...window,entry_ids:['a']}]),null);
  assert.equal(exactOverlapWindow(null,[window]),null);
});

test('逐步顺序按开始日和结束日排序，不改动风险排序的原结果',()=>{
  const late={start:'2026-03-16',end:'2026-04-10'},long={start:'2026-03-02',end:'2026-04-17'},short={start:'2026-03-02',end:'2026-03-27'};
  const original=[late,long,short];
  assert.deepEqual(orderedWindows(original),[short,long,late]);
  assert.deepEqual(original,[late,long,short]);
  assert.deepEqual(orderedWindows([]),[]);
});
test('逐步比较正常显示零超出，重点用加班线，高负荷用最后参考线并计容差',()=>{
  assert.deepEqual(capacityComparison({...local,rank:0,demand:8}),{boundary:'常规参考',threshold:10,excess:0,exceeded:false});
  assert.deepEqual(capacityComparison({...local,rank:1,demand:11}),{boundary:'常规参考',threshold:10,excess:1,exceeded:true});
  assert.deepEqual(capacityComparison({...local,rank:2,demand:12,c1:11}),{boundary:'加班参考',threshold:11,excess:1,exceeded:true});
  assert.deepEqual(capacityComparison(local,{tolerance:1}),{boundary:'高负荷参考',threshold:13,excess:5,exceeded:true});
});


test('未知重叠保留本段参考值，不制造零工时或当前位置',()=>{
  const start=Date.parse('2026-03-16')/86400000,end=Date.parse('2026-03-22')/86400000;
  const rules={hours_per_day:8,average_month:30.4,overtime_hours:36,tolerance:0.5};
  const w=overlapCapacity({start,end},rules,[]);
  assert.equal(w.c0,5);assert.equal(w.c2,7);assert.equal(w.demand,null);assert.equal(w.rank,'pending');
  assert.deepEqual(w.missing_calendar,[2026]);
  const scale=capacityScale(w,rules);assert.equal(scale.demand,null);assert.equal(scale.values[0],5.5);
  assert.equal(overlapCapacity({start:end,end:start},rules,[]),null);
  assert.equal(overlapCapacity({start,end},{...rules,hours_per_day:0},[]),null);
});

test('重叠参考容量与Python引擎一致：节假日、调休、跨年及高加班量',()=>{
  const cases=[
    ['2026-03-16','2026-03-22',36,[]],
    ['2026-03-23','2026-03-27',36,[{year:2026,holidays:['2026-03-23'],makeup_days:[]}]],
    ['2026-03-28','2026-04-10',36,[{year:2026,holidays:['2026-03-29'],makeup_days:['2026-03-29']}]],
    ['2026-12-30','2027-01-04',360,[{year:2026,holidays:[],makeup_days:[]}]],
  ].map(([start,end,overtime,calendars])=>({start,end,calendars,rules:{hours_per_day:8,average_month:30.4,overtime_hours:overtime}}));
  const expected=JSON.parse(execFileSync('python',['-c',`import sys,json
from engine import Capacity,day
cases=json.load(sys.stdin)
print(json.dumps([Capacity(day(c['start']),day(c['end']),c['rules'],c['calendars']).get(day(c['start']),day(c['end'])) for c in cases]))`],{input:JSON.stringify(cases),encoding:'utf-8'}));
  cases.forEach((c,i)=>{
    const w=overlapCapacity({start:Date.parse(c.start)/86400000,end:Date.parse(c.end)/86400000},c.rules,c.calendars);
    [w.n,w.c0,w.c1,w.c2].forEach((v,j)=>assert.ok(Math.abs(v-expected[i][j])<1e-9));
  });
});


test('来源编号跟随申报ID，切换窗口或同项目多段不重新编号',()=>{
  const entries=[{id:'a',project_id:'p',amount:18,unit:'工日'},{id:'b',project_id:'p',amount:20,unit:'工日'},{id:'c',project_id:'q',amount:20,unit:'工日'}];
  const numbers=entryNumbers(entries);
  assert.deepEqual(windowContributions({entry_ids:['b','c']},entries).map(e=>numbers.get(e.id)),[2,3]);
  assert.deepEqual(windowContributions({entry_ids:['a','b']},entries).map(e=>numbers.get(e.id)),[1,2]);
});
