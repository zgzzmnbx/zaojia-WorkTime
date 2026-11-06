"""Deterministic screening only. No legal or automatic settlement conclusions."""
from datetime import date, timedelta
import math

VERSION = '0.1.0'
LABELS = ['常规范围', '需说明额外投入', '重点核查', '高负荷核查']
DEFAULT_CONFIG = dict(hours_per_day=8, days_per_month=None, overtime_hours=36,
                      average_month=30.4, tolerance=0, mode='simulation', rule_version=VERSION)

def empty_state():
    return dict(schema_version=1, projects=[], people=[], entries=[], calendars=[], config=dict(DEFAULT_CONFIG))

def day(value):
    return date.fromisoformat(value) if value else None

def period(start, end):
    return bool(start and end and day(start) <= day(end))

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def convert(amount, unit, cfg):
    if not number(amount) or amount < 0:
        return None
    if unit == '工日': return float(amount)
    if unit == '工时': return amount / cfg['hours_per_day']
    if unit == '人月' and cfg.get('days_per_month'): return amount * cfg['days_per_month']
    return None

def issue(category, level, message, entry_id=None):
    return dict(category=category, level=level, message=message, entry_id=entry_id)

class Capacity:
    def __init__(self, start, end, cfg, calendars):
        self.start, self.cfg = start, cfg
        self.years = {c['year'] for c in calendars}
        holidays = {day(x) for c in calendars for x in c['holidays']}
        makeup = {day(x) for c in calendars for x in c['makeup_days']}
        self.prefix = [0]
        for i in range((end - start).days + 1):
            d = start + timedelta(days=i)
            work = d in makeup or (d not in holidays and d.weekday() < 5)
            self.prefix.append(self.prefix[-1] + int(work))

    def get(self, s, e):
        n = (e-s).days + 1
        c0 = self.prefix[(e-self.start).days+1] - self.prefix[(s-self.start).days]
        c1 = c0 + self.cfg['overtime_hours']/self.cfg['hours_per_day']*n/self.cfg['average_month']
        return n, c0, c1, max(n, c1)

def windows(items, cfg, calendars):
    if not items: return []
    cap = Capacity(min(x['start'] for x in items), max(x['end'] for x in items), cfg, calendars)
    result = []
    for s in sorted({x['start'] for x in items}):
        for e in sorted({x['end'] for x in items}):
            if s > e: continue
            ins = [x for x in items if x['start'] >= s and x['end'] <= e]
            if not ins or min(x['start'] for x in ins) != s or max(x['end'] for x in ins) != e: continue
            n,c0,c1,c2 = cap.get(s,e)
            demand = sum(x['days'] for x in ins)
            rank = next((i for i,c in enumerate((c0,c1,c2)) if demand <= c+cfg['tolerance']+1e-9), 3)
            result.append(dict(start=s.isoformat(), end=e.isoformat(), n=n, demand=demand,
                c0=c0,c1=c1,c2=c2,rank=rank,label=LABELS[rank],entry_ids=[x['id'] for x in ins],
                project_ids=sorted({x['project_id'] for x in ins}),
                basis=' / '.join(sorted({x['basis'] for x in ins})),
                missing_calendar=[y for y in range(s.year,e.year+1) if y not in cap.years],
                excess=max(0,demand-(c0,c1,c2,c2)[rank]), ratio=demand/c2 if c2 else 0))
    return sorted(result, key=lambda w:(w['rank'],w['ratio']), reverse=True)

def prepare_entry(entry, project, cfg, amount_key='amount'):
    amount = convert(entry.get(amount_key),entry.get('unit'),cfg)
    if amount is None: return None, '数量或单位换算依据不完整'
    a,b = entry.get('start'),entry.get('end')
    if a or b:
        if not period(a,b): return None, '人员投入起止日期不完整'
        basis = '人员投入期'
    elif period(project.get('impl_start'),project.get('impl_end')):
        a,b,basis = project['impl_start'],project['impl_end'],'实施期估算'
    else:
        return None, '人员投入期及项目实施期均不完整'
    return dict(id=entry['id'],project_id=project['id'],start=day(a),end=day(b),days=amount,
                basis=basis,dup=entry.get('duplicate','pending')), None

def review_person(person,state):
    cfg = state['config']; projects={p['id']:p for p in state['projects']}
    all_entries=[e for e in state['entries'] if e['person_id']==person['id']]
    entries=[e for e in all_entries if e.get('status') not in ('withdrawn','returned') and e.get('duplicate')!='duplicate']
    findings=[]; items=[]; per_entry=[]
    for entry in entries:
        eid=entry['id']; project=projects[entry['project_id']]
        local=[]
        def add(cat,lv,msg): local.append(issue(cat,lv,msg,eid))
        item,error=prepare_entry(entry,project,cfg)
        if error: add('跨项目','pending',error)
        else:
            items.append(item)
            if item['basis']=='实施期估算': add('实施期','pending','未填人员投入期，仅按实施期估算容量')
        if not period(entry.get('start'),entry.get('end')):
            add('实施期','pending','人员实际投入起止日期待补，期间边界尚不能核实')
        if item is None:
            add('职称计费','pending','投入期间或数量无法核实，职称及计价有效期须补充检查')
        if not period(project.get('impl_start'),project.get('impl_end')):
            add('实施期','pending','缺少完整项目实施期，不能以建设期替代')
        else:
            if not project.get('impl_source'): add('实施期','pending','实施期缺少确认依据')
            if period(project.get('build_start'),project.get('build_end')):
                if project['impl_start']<project['build_start'] or project['impl_end']>project['build_end']:
                    add('实施期','warning','实施期超出建设期，请核对依据')
            if item and item['basis']=='人员投入期':
                if item['start']<day(project['impl_start']) or item['end']>day(project['impl_end']):
                    add('实施期','warning','人员投入发生在项目实施期之外；不能按天数比例自动审减')
        if item:
            w=windows([item],cfg,state['calendars'])[0]
            if w['rank']>0: add('实施期','warning',f'本条投入超过期间常规容量：{w["demand"]:.2f} / {w["c0"]:.2f} 工日（模拟）')
        required=['title','title_source','title_from','title_to']
        if not all(person.get(k) for k in required): add('职称计费','pending','职称、证明依据或有效期不完整')
        elif item and (day(person['title_from'])>item['start'] or day(person['title_to'])<item['end']):
            add('职称计费','warning','职称证明有效期未覆盖投入期间')
        needed=['grade','price','price_unit','basis_title','allowed_grade','basis_price','basis_unit','basis_source','basis_from','basis_to']
        complete=all(entry.get(k) is not None and entry.get(k)!='' for k in needed)
        price_delta=None
        if not complete: add('职称计费','pending','计费等级、单价或对应合同依据不完整')
        else:
            if entry['basis_title']!=person.get('title'): add('职称计费','warning','合同定级依据中的职称与人员职称不一致')
            if entry['grade']!=entry['allowed_grade']: add('职称计费','warning',f'申报等级 {entry["grade"]} 与依据等级 {entry["allowed_grade"]} 不一致')
            if item and (day(entry['basis_from'])>item['start'] or day(entry['basis_to'])<item['end']):
                add('职称计费','warning','计价依据有效期未覆盖投入期间')
            if entry['price_unit']!=entry['basis_unit']: add('职称计费','pending','申报和依据单价单位不同，不能直接比较金额')
            elif entry['price']!=entry['basis_price']:
                add('职称计费','warning',f'申报单价 {entry["price"]:.2f} 与依据单价 {entry["basis_price"]:.2f} 不一致')
            if entry['unit']==entry['price_unit']==entry['basis_unit'] and number(entry.get('amount')):
                price_delta=max(0,entry['price']-entry['basis_price'])*entry['amount']
        per_entry.append(dict(id=eid,findings=local,price_delta=price_delta))
        findings.extend(local)
    grouped={}
    for it in items: grouped.setdefault((it['project_id'],it['start'],it['end']),[]).append(it)
    scenario=[]; has_duplicate=False
    for xs in grouped.values():
        if len(xs)>1 and any(x['dup']!='append' for x in xs):
            has_duplicate=True
            for x in xs: findings.append(issue('跨项目','pending','同项目同期间有待核重复；请明确追加或重复',x['id']))
            confirmed=[x for x in xs if x['dup']=='append']
            uncertain=[x for x in xs if x['dup']!='append']
            scenario.extend(confirmed+[max(uncertain,key=lambda x:x['days'])])
        else: scenario.extend(xs)
    for pid in {x['project_id'] for x in items}:
        spans={(x['start'],x['end']) for x in items if x['project_id']==pid}
        if len(spans)>1: findings.append(issue('跨项目','pending',f'{projects[pid]["name"]} 有多段申报，请核实分段依据'))
    ws=windows(items,cfg,state['calendars']); worst=ws[0] if ws else None
    if worst and worst['rank']>0: findings.append(issue('跨项目','warning',f'最紧时段为{worst["label"]}，仅作模拟筛查'))
    if worst and worst['missing_calendar']:
        findings.append(issue('跨项目','pending','、'.join(map(str,worst['missing_calendar']))+'年日历未维护，工作日估算可能高估或低估'))
    if not person.get('company') or not person.get('code'):
        findings.append(issue('跨项目','pending','人员单位或工号缺失，身份需补充核实'))
    if not entries:
        for category in ('跨项目','实施期','职称计费'):
            findings.append(issue(category,'pending','没有参与本轮筛查的有效申报'))
    occupancy=[]
    for entry in entries:
        current=next((x for x in items if x['id']==entry['id']),None)
        seq=entry.get('review_order') if entry.get('status')=='recognized' else None
        prior=[e for e in entries if e['id']!=entry['id'] and e.get('status')=='recognized' and
               (not seq or e['review_order']<seq)]
        before=[]; reason=None
        if not current or current['basis']!='人员投入期': reason='当前人员期间或数量不完整'
        if has_duplicate: reason='人员存在待核重复，先完成逐条确认'
        for previous in prior:
            x,err=prepare_entry(previous,projects[previous['project_id']],cfg,'recognized_amount')
            if err or x['basis']!='人员投入期': reason='前序认定缺少完整投入分布期间或换算依据'
            else: before.append(x)
        if reason:
            occupancy.append(dict(id=entry['id'],reason=reason)); continue
        merged=windows(before+[current],cfg,state['calendars'])
        candidates=[w for w in merged if current['id'] in w['entry_ids']]
        if not candidates:
            occupancy.append(dict(id=entry['id'],reason='暂无可计算窗口'));continue
        limit=min(candidates,key=lambda w:w['c2']-(w['demand']-current['days']))
        occupied=limit['demand']-current['days']
        remaining=max(0,limit['c2']-occupied)
        occupancy.append(dict(id=entry['id'],start=limit['start'],end=limit['end'],
            prior_ids=[x for x in limit['entry_ids'] if x!=entry['id']],occupied=occupied,
            remaining=remaining,current=current['days'],excess=max(0,current['days']-remaining),
            order_basis='处理序号之前' if seq else '假设排在全部已认定记录之后'))
    summaries={}
    for category in ('跨项目','实施期','职称计费'):
        subset=[f for f in findings if f['category']==category]
        summaries[category]='需核查' if any(f['level']=='warning' for f in subset) else ('待补依据' if subset else '未见异常')
    return dict(person=person,entries=all_entries,active_count=len(entries),windows=ws,worst=worst,
                findings=findings,checks=summaries,entry_checks=per_entry,occupancy=occupancy,
                duplicate_scenario=windows(scenario,cfg,state['calendars'])[0] if has_duplicate and scenario else None,
                pending_count=sum(f['level']=='pending' for f in findings),rule_snapshot=cfg,
                calendar_sources=[dict(year=c['year'],source=c['source']) for c in state['calendars']])

def analyze(state):
    results=[review_person(p,state) for p in state['people']]
    return sorted(results,key=lambda r:((r['worst'] or {}).get('rank',-1),len(r['findings'])),reverse=True)

def validate(state):
    if not isinstance(state,dict) or state.get('schema_version')!=1: raise ValueError('不支持的备份结构版本')
    for key in ('projects','people','entries','calendars'):
        if not isinstance(state.get(key),list): raise ValueError(f'{key} 数据格式错误')
    cfg=state.get('config',{})
    limits={'hours_per_day':(4,12),'overtime_hours':(0,200),'average_month':(28,31),'tolerance':(0,0.5)}
    for key,(lo,hi) in limits.items():
        if not number(cfg.get(key)) or not lo<=cfg[key]<=hi: raise ValueError(f'规则参数 {key} 超出范围')
    if cfg.get('days_per_month') is not None and (not number(cfg['days_per_month']) or not 1<=cfg['days_per_month']<=31):
        raise ValueError('人月折算须为1～31工日，未确认时留空')
    if cfg.get('mode')!='simulation' or cfg.get('rule_version')!=VERSION: raise ValueError('当前版本只支持模拟规则0.1.0')
    for key in ('projects','people','entries'):
        ids=[x.get('id') for x in state[key]]
        if any(not isinstance(x,str) or not x for x in ids) or len(set(ids))!=len(ids): raise ValueError('内部ID缺失或重复')
    for rows,fields in ((state['projects'],('code',)),(state['people'],('company','code'))):
        keys=[tuple(str(x.get(k,'')).strip() for k in fields) for x in rows]
        if len(set(keys))!=len(keys): raise ValueError('项目编号或同单位工号重复')
        if any(not x.get('name','').strip() or not x.get('code','').strip() for x in rows): raise ValueError('名称与编号必填')
    if any(not p.get('company','').strip() for p in state['people']): raise ValueError('人员所属单位必填')
    all_objects=state['projects']+state['people']+state['entries']
    for obj in all_objects:
        for start,end in (('build_start','build_end'),('impl_start','impl_end'),('start','end'),('title_from','title_to'),('basis_from','basis_to')):
            for k in (start,end):
                if obj.get(k):
                    d=day(obj[k])
                    if not 2000<=d.year<=2100: raise ValueError('日期须在2000～2100年之间')
            if obj.get(start) and obj.get(end):
                if day(obj[start])>day(obj[end]): raise ValueError('结束日期不能早于开始日期')
                if (day(obj[end])-day(obj[start])).days>3660: raise ValueError('单条期间超过10年，请核对日期')
        if obj.get('submitted_at'): day(obj['submitted_at'])
    pids={x['id'] for x in state['projects']}; people={x['id'] for x in state['people']}; orders=[]
    for e in state['entries']:
        if e.get('project_id') not in pids or e.get('person_id') not in people: raise ValueError('申报引用不存在的人员或项目')
        for key in ('amount','price','basis_price','recognized_amount'):
            if e.get(key) is not None and (not number(e[key]) or e[key]<0): raise ValueError('数量与单价须为非负有限数')
        if e.get('amount')==0: raise ValueError('申报数量须大于0')
        for key in ('unit','price_unit','basis_unit'):
            if e.get(key) not in ('工日','工时','人月',None,''): raise ValueError('未知计量单位')
        if e.get('unit') not in ('工日','工时','人月'): raise ValueError('申报单位必填')
        if e.get('duplicate') not in ('pending','append','duplicate'): raise ValueError('重复状态无效')
        if e.get('status') not in ('pending','needs_info','recognized','returned','withdrawn'): raise ValueError('复核状态无效')
        if e.get('status')!='pending' and (not e.get('reviewer','').strip() or not e.get('review_note','').strip()): raise ValueError('处理状态需填写复核人和依据说明')
        if e.get('status')=='recognized':
            if not number(e.get('recognized_amount')) or not number(e.get('amount')) or e['recognized_amount']>e['amount']: raise ValueError('认定数量必填且不得超过申报数量')
            if e.get('duplicate')=='duplicate': raise ValueError('已确认为重复的条目不能认定')
            if not isinstance(e.get('review_order'),int) or isinstance(e.get('review_order'),bool) or e['review_order']<1: raise ValueError('已认定记录需正整数处理序号')
            orders.append(e['review_order'])
    if len(orders)!=len(set(orders)): raise ValueError('已认定记录处理序号重复')
    years=[]
    for c in state['calendars']:
        if not isinstance(c.get('year'),int) or not 2000<=c['year']<=2100 or not c.get('source','').strip(): raise ValueError('日历年份或依据缺失')
        years.append(c['year'])
        h,m=c.get('holidays'),c.get('makeup_days')
        if not isinstance(h,list) or not isinstance(m,list): raise ValueError('日历格式不正确')
        if set(h)&set(m): raise ValueError('同一天不能同时为休息与补班')
        if any(day(x).year!=c['year'] for x in h+m): raise ValueError('日历日期与年份不一致')
    if len(years)!=len(set(years)): raise ValueError('日历年份重复')
    return state
