from engine import empty_state

def demo_state():
    s=empty_state()
    s['projects']=[dict(id=f'p{i}',code=f'DEMO-0{i}',name=name,
        build_start='2026-01-01',build_end='2026-12-31',impl_start='2026-03-01',impl_end='2026-04-30',
        impl_source='模拟实施计划，仅供演示') for i,name in enumerate([
            '管网巡检数字化','工程数据治理','设备监测平台','结算协同系统','运维知识平台','数据安全治理'],1)]
    s['people']=[dict(id=f'u{i}',code=f'Y0{i:02}',name=name,company=company,title='高级工程师',
        title_source='模拟职称证明',title_from='2025-01-01',title_to='2027-12-31') for i,(name,company) in enumerate([
            ('林明远','示例技术公司'),('陈思宁','示例技术公司'),('周启航','示例软件公司'),
            ('赵文清','示例软件公司'),('林明远','示例咨询公司'),('许嘉禾','示例技术公司'),
            ('宋亦安','示例技术公司'),('顾承泽','示例软件公司'),('韩知行','示例咨询公司'),
            ('陆景和','示例技术公司'),('魏启明','示例软件公司'),('沈若岚','示例咨询公司')],1)]
    rows=[('u1','p1','03-02','03-27',18),('u1','p2','03-16','04-10',20),('u1','p3','03-23','04-17',20),
          ('u2','p1','03-02','03-27',8),('u2','p2','03-16','04-10',7),
          ('u3','p1','03-02','03-13',8),('u3','p3','03-16','03-27',9),
          ('u4','p4','02-16','03-13',15),('u5','p2','04-06','04-17',5),
          ('u6','p4',None,None,2)]
    # Identical windows make levels directly comparable: C0=30, C1≈35.92, C2=40.
    for person,amounts in [('u7',[8,8,8,8]),('u8',[10,10,9,9]),
                           ('u9',[12,12,12,12]),('u10',[6,6,6,6]),
                           ('u11',[80,80,72,72])]:
        rows.extend((person,f'p{j}','03-02','04-10',amount) for j,amount in zip(range(3,7),amounts))
    # Overall total fits the long period, but a nested fortnight is overloaded.
    rows.extend([('u12','p3','03-02','04-30',12),('u12','p4','03-16','03-27',9),
                 ('u12','p5','03-16','03-27',9),('u12','p6','04-13','04-24',6)])
    for i,(person,project,start,end,amount) in enumerate(rows,1):
        s['entries'].append(dict(id=f'e{i}',person_id=person,project_id=project,
            start='2026-'+start if start else '',end='2026-'+end if end else '',amount=amount,
            unit='人月' if person=='u6' else ('工时' if person=='u11' else '工日'),submitted_at='2026-05-06',
            grade='高级',price=1600,price_unit='工日',basis_title='高级工程师',allowed_grade='高级',
            basis_price=1600,basis_unit='工日',basis_source='模拟合同：高级工程师1600元/工日',
            basis_from='2026-01-01',basis_to='2026-12-31',duplicate='append',status='pending',
            recognized_amount=None,reviewer='',review_note='',review_order=None))
    for entry in s['entries']:
        if entry['person_id']=='u11':
            entry.update(price=200,price_unit='工时',basis_price=200,basis_unit='工时',
                         basis_source='模拟合同：高级工程师200元/工时')
    s['entries'][0].update(status='recognized',recognized_amount=18,reviewer='模拟审核员',review_note='模拟先序认定，非实际审核',review_order=1)
    s['entries'][7].update(grade='专家级',price=2200)
    s['calendars']=[dict(year=2026,holidays=[],makeup_days=[],source='模拟日历：仅周一至周五工作，不代表2026年实际放假安排')]
    return s
