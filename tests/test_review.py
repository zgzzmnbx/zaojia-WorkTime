import copy, json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from engine import *
from sample_data import demo_state
from server import Store, Conflict, handler_factory

class RulesTests(unittest.TestCase):
    def setUp(self): self.s=demo_state()
    def result(self,p='u1'): return review_person(next(x for x in self.s['people'] if x['id']==p),self.s)
    def test_demo_three_checks(self):
        rs={r['person']['id']:r for r in analyze(validate(self.s))}
        self.assertEqual(rs['u1']['worst']['rank'],3)
        self.assertEqual(rs['u2']['worst']['rank'],0)
        self.assertEqual(rs['u3']['worst']['rank'],0)
        for person,rank,total in [('u7',1,32),('u8',2,38),('u9',3,48),('u10',0,24),('u11',2,38),('u12',3,18)]:
            self.assertEqual(rs[person]['worst']['rank'],rank,person)
            self.assertEqual(rs[person]['worst']['demand'],total,person)
        self.assertEqual(rs['u4']['checks']['实施期'],'需核查')
        self.assertEqual(rs['u4']['checks']['职称计费'],'需核查')
        self.assertEqual(rs['u6']['checks'],{'跨项目':'待补依据','实施期':'待补依据','职称计费':'待补依据'})
    def test_same_name_not_merged(self):
        self.assertEqual(len(self.result('u1')['entries']),3)
        self.assertEqual(len(self.result('u5')['entries']),1)
    def test_entered_amount_drives_windows_without_review(self):
        for e in self.s['entries']:
            if e['person_id']=='u1':
                e['status']='pending'
                for key in ('recognized_amount','review_order','reviewer','review_note'):e.pop(key,None)
        validate(self.s)
        self.assertEqual(self.result()['worst']['demand'],58)
    def test_legacy_recognition_does_not_change_main_windows(self):
        before=self.result()['windows']
        self.s['entries'][0]['recognized_amount']=5
        self.s['entries'][0]['review_order']=999
        self.assertEqual(self.result()['windows'],before)
    def test_direct_edit_below_legacy_recognition(self):
        self.s['entries'][0].update(status='pending',amount=12)
        validate(self.s)
        whole=next(w for w in self.result()['windows'] if w['start']=='2026-03-02' and w['end']=='2026-04-17')
        self.assertEqual(whole['demand'],52)
    def test_separate_periods(self): self.assertEqual(self.result('u3')['worst']['rank'],0)
    def test_nested_window_detects_local_overload(self):
        self.s['entries']=self.s['entries'][:2]
        self.s['entries'][0].update(start='2026-01-05',end='2026-04-30',amount=20)
        self.s['entries'][1].update(start='2026-02-02',end='2026-03-27',amount=52)
        w=self.result()['worst'];self.assertEqual(w['start'],'2026-02-02');self.assertEqual(w['rank'],2)
    def test_hour_conversion(self): self.assertEqual(convert(80,'工时',DEFAULT_CONFIG),10)
    def test_unknown_unit_not_converted(self): self.assertIsNone(convert(80,'天',DEFAULT_CONFIG))
    def test_month_unknown_and_configured(self):
        self.assertIsNone(convert(2,'人月',DEFAULT_CONFIG))
        self.assertIsNone(convert(2,'人月',{**DEFAULT_CONFIG,'days_per_month':20}))
    def test_legacy_unit_is_preserved_but_not_counted(self):
        entry=self.s['entries'][0]
        entry['unit']='人月';self.s['config']['days_per_month']=20
        result=self.result()
        self.assertTrue(all(entry['id'] not in w['entry_ids'] for w in result['windows']))
        self.assertTrue(any('更正单位' in f['message'] for f in result['findings']))
        self.assertEqual(entry['amount'],18)
    def test_nan_rejected(self):
        self.s['entries'][0]['amount']=float('nan')
        with self.assertRaises(ValueError): validate(self.s)
    def test_infinity_rejected(self):
        self.s['entries'][0]['price']=float('inf')
        with self.assertRaises(ValueError): validate(self.s)
    def test_half_date_not_fallback(self):
        self.s['entries'][0]['end']=''
        r=self.result();self.assertFalse(any('e1' in w['entry_ids'] for w in r['windows']))
        self.assertGreater(r['pending_count'],0)
    def test_no_build_period_fallback(self):
        self.s['entries'][0].update(start='',end='')
        self.s['projects'][0].update(impl_start='',impl_end='')
        self.assertFalse(any('e1' in w['entry_ids'] for w in self.result()['windows']))
    def test_implementation_estimate_labeled(self):
        self.s['entries'][0].update(start='',end='')
        self.assertTrue(any('实施期估算' in w['basis'] for w in self.result()['windows']))
        self.assertEqual(self.result()['checks']['实施期'],'待补依据')
    def test_impl_evidence_missing(self):
        self.s['projects'][0]['impl_source']='';self.assertEqual(self.result()['checks']['实施期'],'待补依据')
    def test_title_expiry(self):
        self.s['people'][0]['title_to']='2026-03-03'
        self.assertTrue(any('职称证明有效期' in f['message'] for f in self.result()['findings']))
    def test_title_mapping(self):
        self.s['entries'][0]['basis_title']='中级工程师'
        self.assertEqual(self.result()['checks']['职称计费'],'需核查')
    def test_price_difference(self):
        r=self.result('u4');self.assertEqual(r['entry_checks'][0]['price_delta'],9000)
    def test_price_unit_difference_not_multiplied(self):
        self.s['entries'][7]['basis_unit']='人月';self.assertIsNone(self.result('u4')['entry_checks'][0]['price_delta'])
    def test_mixed_duplicate_preserves_append(self):
        base=copy.deepcopy(self.s['entries'][0]);self.s['entries']=[]
        for i,(amount,dup) in enumerate([(10,'pending'),(5,'append'),(10,'pending')]):
            self.s['entries'].append({**base,'id':f'x{i}','amount':amount,'duplicate':dup,'status':'pending'})
        r=self.result();self.assertEqual(r['worst']['demand'],25);self.assertEqual(r['duplicate_scenario']['demand'],15)
    def test_excluded_duplicate(self):
        self.s['entries'][1]['duplicate']='duplicate'
        self.assertFalse(any('e2' in w['entry_ids'] for w in self.result()['windows']))
    def test_withdrawn_releases_capacity(self):
        before=next(o for o in self.result()['occupancy'] if o['id']=='e2')['remaining']
        self.s['entries'][0].update(status='withdrawn')
        after=next(o for o in self.result()['occupancy'] if o['id']=='e2')['remaining']
        self.assertGreater(after,before)
    def test_recognition_edit_recomputes(self):
        before=next(o for o in self.result()['occupancy'] if o['id']=='e2')['remaining']
        self.s['entries'][0]['recognized_amount']=5
        after=next(o for o in self.result()['occupancy'] if o['id']=='e2')['remaining']
        self.assertGreater(after,before)
    def test_overlapping_flexible_prior_not_all_deducted(self):
        self.s['entries']=self.s['entries'][:2]
        self.s['entries'][0].update(start='2026-03-01',end='2026-04-30',amount=10,recognized_amount=10)
        self.s['entries'][1].update(start='2026-03-16',end='2026-03-20',amount=2)
        o=next(o for o in self.result()['occupancy'] if o['id']=='e2')
        self.assertEqual(o['occupied'],0)
        self.assertGreater(o['remaining'],5)
    def test_recognition_requires_evidence(self):
        self.s['entries'][0]['review_note']=''
        with self.assertRaises(ValueError):validate(self.s)
    def test_duplicate_review_order_rejected(self):
        self.s['entries'][1].update(status='recognized',recognized_amount=10,review_order=1,reviewer='A',review_note='依据')
        with self.assertRaises(ValueError):validate(self.s)
    def test_recognition_not_more_than_claim(self):
        self.s['entries'][0]['recognized_amount']=19
        with self.assertRaises(ValueError):validate(self.s)
    def test_calendar_conflict(self):
        self.s['calendars'][0].update(holidays=['2026-03-05'],makeup_days=['2026-03-05'])
        with self.assertRaises(ValueError):validate(self.s)
    def test_calendar_missing_warns(self):
        self.s['calendars']=[]
        self.assertTrue(any('高估或低估' in f['message'] for f in self.result()['findings']))
    def test_calendar_workday(self):
        c=Capacity(date(2026,3,2),date(2026,3,13),DEFAULT_CONFIG,[dict(year=2026,holidays=['2026-03-05','2026-03-06'],makeup_days=['2026-03-07'])])
        self.assertEqual(c.get(date(2026,3,2),date(2026,3,13))[1],9)
    def test_missing_all_data_not_green(self):
        self.s['entries']=[];r=self.result()
        self.assertIsNone(r['worst']);self.assertTrue(all(v=='待补依据' for v in r['checks'].values()))
    def test_invalid_reference(self):
        self.s['entries'][0]['person_id']='missing'
        with self.assertRaises(ValueError):validate(self.s)
    def test_same_company_code_duplicate(self):
        self.s['people'][1].update(code='Y001')
        with self.assertRaises(ValueError):validate(self.s)
    def test_negative_amount(self):
        self.s['entries'][0]['amount']=-1
        with self.assertRaises(ValueError):validate(self.s)
    def test_bad_dates(self):
        self.s['entries'][0]['start']='2026-02-30'
        with self.assertRaises(ValueError):validate(self.s)
    def test_full_precision_boundary(self):
        self.s['entries']=self.s['entries'][:1]
        self.s['entries'][0].update(start='2026-03-02',end='2026-03-06',amount=5.00001,recognized_amount=5)
        self.assertEqual(self.result()['worst']['rank'],1)
    def test_snapshot_and_determinism(self):
        before=copy.deepcopy(self.s);self.assertEqual(analyze(self.s),analyze(self.s));self.assertEqual(self.s,before)

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ledger.sqlite3';self.store=Store(self.path,True)
    def tearDown(self):self.tmp.cleanup()
    def test_persist_reopen(self):
        rev,s=self.store.read();s['people'][0]['name']='修改后的模拟人员';self.store.save(s,rev,'审核A','更正姓名')
        self.assertEqual(Store(self.path).read()[1]['people'][0]['name'],'修改后的模拟人员')
        self.assertEqual(self.store.revision(0)['people'][0]['name'],'林明远')
    def test_stale_write_conflict(self):
        rev,s=self.store.read();self.store.save(s,rev,'审核A','修改')
        with self.assertRaises(Conflict):self.store.save(s,rev,'审核B','过期修改')
        self.assertEqual(self.store.read()[0],1)
    def test_project_periods_must_be_ordered_and_implementation_inside_construction(self):
        rev, original = self.store.read()
        for patch, message in (
            ({'build_end': '2025-12-31'}, '建设结束日期不能早于建设开始日期'),
            ({'impl_end': '2026-02-28'}, '实施结束日期不能早于实施开始日期'),
            ({'impl_start': '2025-12-31'}, '实施日期不能早于建设开始日期'),
            ({'impl_start': '', 'impl_end': '2027-01-01'}, '实施日期不能晚于建设结束日期'),
        ):
            state = copy.deepcopy(original)
            state['projects'][0].update(patch)
            with self.assertRaisesRegex(ValueError, message):
                self.store.save(state, rev, '审核A', '修改项目')
            self.assertEqual(self.store.read(), (rev, original))
        original['projects'][0].update(impl_start='2026-01-01', impl_end='2026-12-31')
        self.assertEqual(self.store.save(original, rev, '审核A', '修改项目'), rev + 1)
    def test_restore_backup_and_log(self):
        rev,s=self.store.read();self.store.save(empty_state(),rev,'审核A','恢复',True)
        backups=list((self.path.parent/'backups').glob('*.json'));self.assertEqual(len(backups),1)
        self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8'))['state'],s)
        self.assertEqual(self.store.history()[0]['action'],'恢复')
    def test_bad_restore_preserves_current(self):
        before=self.store.read()
        with self.assertRaises(ValueError):self.store.save({},0,'审核A','坏备份',True)
        self.assertEqual(self.store.read(),before)
    def test_separate_demo_and_real(self):
        real=Store(self.path.parent/'real.sqlite3');self.assertEqual(real.read()[1]['entries'],[])
        self.assertEqual(len(self.store.read()[1]['entries']),34)
    def test_save_rejects_new_unsupported_unit_without_changing_ledger(self):
        revision,state=self.store.read();before=copy.deepcopy(state)
        state['entries'][0]['unit']='人月'
        with self.assertRaisesRegex(ValueError,'仅支持工日和工时'):
            self.store.save(state,revision,'测试','更改单位')
        self.assertEqual(self.store.read(),(revision,before))

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        stores={False:Store(root/'real.db'),True:Store(root/'demo.db',True)}
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_factory(stores));self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def test_api_demo_and_csv(self):
        with urllib.request.urlopen(self.base+'/api/demo/state') as r:data=json.load(r)
        self.assertEqual(len(data['results']),12)
        with urllib.request.urlopen(self.base+'/api/demo/export') as r:
            self.assertTrue(r.read().startswith(b'\xef\xbb\xbf'))
        with urllib.request.urlopen(self.base+'/api/state') as r:self.assertEqual(json.load(r)['state']['people'],[])
    def test_health_distinguishes_app_and_rules(self):
        with urllib.request.urlopen(self.base+'/api/health') as r:data=json.load(r)
        self.assertEqual(data['app_version'],json.loads((Path(__file__).resolve().parents[1]/'package.json').read_text(encoding='utf-8'))['version'])
        self.assertEqual(data['rule_version'],data['version'])
    def test_cross_origin_post_blocked(self):
        req=urllib.request.Request(self.base+'/api/save',data=b'{}',headers={'Origin':'https://other.example','Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code,403)
    def test_invalid_json_no_mutation(self):
        req=urllib.request.Request(self.base+'/api/save',data=b'{bad',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code,400)
    def test_post_save_refresh(self):
        s=demo_state();payload=dict(state=s,revision=0,actor='测试审核员',action='首次录入')
        req=urllib.request.Request(self.base+'/api/save',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r)['revision'],1)
        with urllib.request.urlopen(self.base+'/api/state') as r:self.assertEqual(len(json.load(r)['state']['entries']),34)

if __name__=='__main__':unittest.main()
