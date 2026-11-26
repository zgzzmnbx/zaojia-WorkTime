import base64, copy, csv, io, tempfile, unittest
import json, threading, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from engine import empty_state, analyze
from sample_data import demo_state
from project_io import FIELDS, COMPACT_FIELDS, GRID_FIELDS, DATED_GRID_FIELDS, DATED_GRID_HEADERS, NS, import_preview, repair_import_row, scoped_report, export_options, selection_template, refresh_template, person_choice, read_xlsx, certificate_date_hint, certificate_date_formula
from server import Store, Conflict, handler_factory

TEMPLATE=Path(__file__).resolve().parents[1]/'public/project-hours-template.xlsx'

def filled(rows, formula=False, fields=FIELDS):
    """Populate a disposable copy of the shipped template for integration tests."""
    out=io.BytesIO()
    with ZipFile(TEMPLATE) as source, ZipFile(out,'w',ZIP_DEFLATED) as dest:
        for item in source.infolist():
            raw=source.read(item.filename)
            if item.filename=='xl/worksheets/sheet1.xml':
                root=ET.fromstring(raw); data=root.find('s:sheetData',NS)
                for old in list(data): data.remove(old)
                for i,record in enumerate([dict((key,label) for label,key in fields)]+rows,1):
                    row=ET.SubElement(data,'{'+NS['s']+'}row',r=str(i))
                    for j,(_,key) in enumerate(fields):
                        col=chr(65+j); val=record.get(key,'')
                        cell=ET.SubElement(row,'{'+NS['s']+'}c',r=f'{col}{i}',t='inlineStr')
                        inline=ET.SubElement(cell,'{'+NS['s']+'}is');ET.SubElement(inline,'{'+NS['s']+'}t').text=str(val)
                        if formula and key=='amount' and i>1: ET.SubElement(cell,'{'+NS['s']+'}f').text='1+1'
                raw=ET.tostring(root)
            dest.writestr(item,raw)
    return base64.b64encode(out.getvalue()).decode()

BASE=dict(name='测试人员',company='测试单位',code='001',start='2026-03-02',end='2026-03-06',amount=5,unit='工日')

class ImportTests(unittest.TestCase):
    def test_compact_two_fields_inherit_current_person_and_common_basis(self):
        s=demo_state(); person=s['people'][0];before=copy.deepcopy(s)
        r=import_preview(s,filled([dict(person_choice=person_choice(person),amount=8)],fields=COMPACT_FIELDS),
                         dict(start='2026-03-02',end='2026-03-06',unit='工时',price=100,price_unit='工时'))
        self.assertEqual(r['errors'],[]); row=r['rows'][0]
        self.assertEqual(row['person_id'],person['id']);self.assertEqual(row['data']['title'],person['title'])
        self.assertEqual(row['data']['unit'],'工时');self.assertEqual(row['data']['price'],100)
        self.assertIn('start',row['inherited']);self.assertEqual(s,before)
    def test_compact_overrides_common_and_new_person_identity(self):
        r=import_preview(empty_state(),filled([{**BASE,'unit':'工时','start':'2026-03-03'}],fields=COMPACT_FIELDS),
                         dict(start='2026-03-02',end='2026-03-06',unit='工日',company='统一单位'))
        self.assertEqual(r['errors'],[]);self.assertEqual(r['rows'][0]['data']['unit'],'工时')
        self.assertEqual(r['rows'][0]['data']['start'],'2026-03-03');self.assertEqual(r['new_people'],1)
    def test_all_import_layouts_reject_month_units(self):
        for fields in (FIELDS, COMPACT_FIELDS, GRID_FIELDS, DATED_GRID_FIELDS):
            row={**BASE,'person_choice':'新增人员','title':'技术专家','validity':'固定时间段内有效',
                 'title_from':'2025-01-01','title_to':'2027-12-31','unit':'人月'}
            if fields == COMPACT_FIELDS: row['person_choice']=''
            if fields == GRID_FIELDS: row['validity']='2025/1/1 至 2027/12/31'
            result=import_preview(empty_state(),filled([row],fields=fields))
            self.assertTrue(result['errors'])
            self.assertTrue(any(issue['field']=='unit' for error in result['errors'] for issue in error['issues']))
    def test_compact_missing_dates_stale_choice_and_identity_conflict(self):
        s=demo_state(); choice=person_choice(s['people'][0])
        for row,defaults in [(dict(person_choice=choice,amount=1),dict(unit='工日')),
                             (dict(person_choice='过期人员',amount=1),dict(unit='工日',start='2026-03-02',end='2026-03-06')),
                             (dict(person_choice=choice,amount=1,name='另一个人'),dict(unit='工日',start='2026-03-02',end='2026-03-06'))]:
            self.assertTrue(import_preview(s,filled([row],fields=COMPACT_FIELDS),defaults)['errors'])
    def test_template_dropdown_uses_only_current_ledger_and_bounded_range(self):
        s=demo_state();raw=selection_template(TEMPLATE.read_bytes(),s)
        with ZipFile(io.BytesIO(raw)) as z:
            roster=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
            self.assertEqual(len(roster.findall('s:sheetData/s:row',NS)),len(s['people'])+2)
            self.assertIn(person_choice(s['people'][0]),''.join(roster.itertext()))
            main=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            rule=next(x for x in main.findall('s:dataValidations/s:dataValidation',NS) if x.get('sqref')=='A2:A2001')
            self.assertIn(f'$A${len(s["people"])+2}',rule.findtext('s:formula1',namespaces=NS))
            formatting=main.find('s:conditionalFormatting',NS)
            self.assertEqual(formatting.get('sqref'),'B2:G2001')
            self.assertEqual(formatting.findtext('s:cfRule/s:formula',namespaces=NS),'AND($A2<>"",$A2<>"新增人员")')
        with ZipFile(io.BytesIO(selection_template(TEMPLATE.read_bytes(),empty_state()))) as z:
            self.assertNotIn(s['people'][0]['name'],z.read('xl/worksheets/sheet2.xml').decode())

    def test_grid_formulas_use_current_ledger_and_do_not_create_extra_claims(self):
        state = demo_state()
        raw = selection_template(TEMPLATE.read_bytes(), state)
        out = io.BytesIO()
        ns = '{' + NS['s'] + '}'
        with ZipFile(io.BytesIO(raw)) as source, ZipFile(out, 'w', ZIP_DEFLATED) as target:
            for item in source.infolist():
                content = source.read(item)
                if item.filename == 'xl/worksheets/sheet1.xml':
                    sheet = ET.fromstring(content)
                    def cell(ref):
                        return sheet.find(f'.//s:c[@r="{ref}"]', NS)
                    self.assertEqual([cell(f'{chr(65+i)}1').findtext('s:v', namespaces=NS)
                                      for i in range(len(DATED_GRID_HEADERS))], DATED_GRID_HEADERS)
                    self.assertIn('VLOOKUP', cell('B2').findtext('s:f', namespaces=NS))
                    cell('B2').find('s:v', NS).text = '过期的缓存姓名'
                    self.assertIn('无需填写', cell('L2').findtext('s:f', namespaces=NS))
                    cell('L2').find('s:v', NS).text = '无需填写'
                    cell('A2').set('t', 'str')
                    ET.SubElement(cell('A2'), ns+'v').text = person_choice(state['people'][0])
                    ET.SubElement(cell('H2'), ns+'v').text = '8'
                    cell('B3').find('s:v', NS).text = '空白行里的缓存'
                    formula = cell('B3').find('s:f', NS)
                    formula.set('t', 'shared')
                    formula.set('si', '0')
                    formula.text = None
                    content = ET.tostring(sheet)
                target.writestr(item, content)
        encoded = base64.b64encode(out.getvalue()).decode()
        defaults = dict(start='2026/3/2', end='2026/3/6', unit='工时')
        for file in (encoded, base64.b64encode(refresh_template(encoded, state)).decode()):
            result = import_preview(state, file, defaults)
            self.assertEqual(result['errors'], [])
            self.assertEqual(len(result['rows']), 1)
            self.assertEqual(result['rows'][0]['person_id'], state['people'][0]['id'])
            self.assertEqual(result['rows'][0]['data']['name'], state['people'][0]['name'])
            self.assertEqual(result['rows'][0]['data']['amount'], 8)

    def test_grid_explicit_new_preserves_text_code_and_validity(self):
        row = {**BASE, 'person_choice':'新增人员', 'title':'技术专家', 'validity':'2025/4/4 至 2026/4/4'}
        result = import_preview(empty_state(), filled([row], fields=GRID_FIELDS))
        self.assertEqual(result['errors'], [])
        data = result['rows'][0]['data']
        self.assertEqual((data['code'], data['title_from'], data['title_to']), ('001', '2025-04-04', '2026-04-04'))
        row['person_choice'] = ''
        self.assertTrue(import_preview(empty_state(), filled([row], fields=GRID_FIELDS))['errors'])

    def test_certificate_template_has_typed_dates_and_automatic_recalculation(self):
        state=demo_state()
        state['people'][1].update(title_permanent=True,title_from='',title_to='')
        state['people'][2].update(title_from='',title_to='')
        before=copy.deepcopy(state)
        with ZipFile(io.BytesIO(selection_template(TEMPLATE.read_bytes(),state))) as z:
            roster=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
            def text(ref):
                cell=roster.find(f'.//s:c[@r="{ref}"]',NS)
                return ''.join(cell.itertext())
            self.assertEqual(text('F3'),'固定时间段内有效')
            self.assertEqual((text('H3'),text('I3')),('45658','46752'))
            self.assertEqual(roster.find('.//s:c[@r="H3"]',NS).get('t'),None)
            self.assertEqual((text('F4'),text('H4'),text('I4')),('长期有效','',''))
            self.assertEqual((text('F5'),text('H5'),text('I5')),('待补','',''))
            self.assertEqual(text('I1'),'证书有效结束')
            main=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(main.find('.//s:c[@r="L2"]/s:f',NS).text,certificate_date_formula(2,8))
            self.assertEqual(main.find('.//s:c[@r="M2001"]/s:f',NS).text,certificate_date_formula(2001,9))
            self.assertEqual(ET.fromstring(z.read('xl/workbook.xml')).find('s:calcPr',NS).get('calcMode'),'auto')
        self.assertEqual(state,before)

    def test_refresh_upgrades_old_date_hints_and_preserves_manual_dates(self):
        state=demo_state();raw=selection_template(TEMPLATE.read_bytes(),state);out=io.BytesIO()
        with ZipFile(io.BytesIO(raw)) as source,ZipFile(out,'w',ZIP_DEFLATED) as target:
            for item in source.infolist():
                content=source.read(item)
                if item.filename=='xl/worksheets/sheet1.xml':
                    sheet=ET.fromstring(content)
                    for ref in ('L2','M2'):
                        cell=sheet.find(f'.//s:c[@r="{ref}"]',NS)
                        cell.find('s:f',NS).text=certificate_date_hint(2)
                        cell.find('s:v',NS).text='无需填写'
                    shared=sheet.find('.//s:c[@r="L2"]/s:f',NS)
                    shared.attrib.update(t='shared',si='0',ref='L2:L2001')
                    for ref,value in [('L3','2025/4/4'),('M3','2026/4/4')]:
                        cell=sheet.find(f'.//s:c[@r="{ref}"]',NS)
                        cell.remove(cell.find('s:f',NS));cell.set('t','str')
                        cell.find('s:v',NS).text=value
                    content=ET.tostring(sheet)
                target.writestr(item,content)
        refreshed=refresh_template(base64.b64encode(out.getvalue()).decode(),state)
        with ZipFile(io.BytesIO(refreshed)) as z:
            sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            for ref,index in [('L2',8),('M2',9)]:
                cell=sheet.find(f'.//s:c[@r="{ref}"]',NS)
                self.assertEqual(cell.find('s:f',NS).text,certificate_date_formula(2,index))
                self.assertFalse(cell.findtext('s:v',namespaces=NS))
            self.assertEqual(sheet.find('.//s:c[@r="L2"]/s:f',NS).get('ref'),'L2:L2001')
            self.assertEqual(sheet.find('.//s:c[@r="L3"]/s:v',NS).text,'2025/4/4')
            self.assertEqual(sheet.find('.//s:c[@r="M3"]/s:v',NS).text,'2026/4/4')

    def test_unknown_certificate_date_formula_is_not_trusted(self):
        row={**BASE,'person_choice':person_choice(demo_state()['people'][0]),'name':'','company':'','code':''}
        encoded=filled([row],fields=DATED_GRID_FIELDS);out=io.BytesIO()
        with ZipFile(io.BytesIO(base64.b64decode(encoded))) as source,ZipFile(out,'w',ZIP_DEFLATED) as target:
            for item in source.infolist():
                content=source.read(item)
                if item.filename=='xl/worksheets/sheet1.xml':
                    sheet=ET.fromstring(content)
                    cell=sheet.find('.//s:c[@r="L2"]',NS)
                    ET.SubElement(cell,'{'+NS['s']+'}f').text='TODAY()'
                    content=ET.tostring(sheet)
                target.writestr(item,content)
        result=import_preview(demo_state(),base64.b64encode(out.getvalue()).decode())
        self.assertTrue(result['errors'])

    def test_new_excel_validity_and_units(self):
        row = {**BASE, 'person_choice':'新增人员', 'title':'技术专家', 'validity':'固定时间段内有效',
               'title_from':'2025/4/4', 'title_to':'2026/4/4'}
        def parse(patch):
            return import_preview(empty_state(), filled([{**row, **patch}], fields=DATED_GRID_FIELDS))
        result = parse({})
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['rows'][0]['data']['title_to'], '2026-04-04')
        for patch in ({'title_to':''}, {'title_to':'2025/4/3'}, {'unit':'人月'}, {'validity':'长期有效'}):
            self.assertTrue(parse(patch)['errors'])
        self.assertFalse(parse({'validity':'长期有效','title_from':'','title_to':''})['errors'])
        self.assertFalse(parse({'validity':'','title_from':'','title_to':''})['errors'])
        self.assertFalse(parse({'validity':'长期有效','title_from':'无需填写','title_to':'无需填写'})['errors'])

    def test_template_and_preview_do_not_mutate(self):
        s=empty_state(); before=copy.deepcopy(s)
        result=import_preview(s,filled([BASE,{**BASE,'amount':8,'unit':'工时'}]))
        self.assertEqual(result['errors'],[]); self.assertEqual(len(result['rows']),2)
        self.assertEqual(result['new_people'],1); self.assertEqual(result['rows'][0]['data']['code'],'001')
        self.assertEqual(s,before)
    def test_empty_template(self):
        r=import_preview(empty_state(),base64.b64encode(TEMPLATE.read_bytes()).decode())
        self.assertTrue(r['errors']);self.assertEqual(r['rows'],[])
    def test_excel_serial_dates_and_optional_basis(self):
        r=import_preview(empty_state(),filled([{**BASE,'start':46083,'end':46087}]))
        self.assertFalse(r['errors']);self.assertEqual(r['rows'][0]['data']['start'],'2026-03-02')
        self.assertIsNone(r['rows'][0]['data']['basis_price'])
    def test_bad_rows_block_with_row_numbers(self):
        for patch in [dict(end='2026-01-01'),dict(amount=-2),dict(amount=0),dict(unit='天'),dict(start=''),dict(price='NaN')]:
            r=import_preview(empty_state(),filled([{**BASE,**patch}]))
            self.assertEqual(r['errors'][0]['row'],2,patch)
    def test_formula_and_malformed_rejected(self):
        result = import_preview(empty_state(),filled([BASE],True))
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['errors'][0]['issues'][0]['field'], 'amount')
        self.assertEqual(result['errors'][0]['data']['amount'], '=1+1')
        with self.assertRaises(ValueError): import_preview(empty_state(),'not-base64')
    def test_mixed_import_preserves_problem_row_and_repairs_multiple_fields(self):
        state = demo_state()
        before = copy.deepcopy(state)
        selected = dict(person_choice=person_choice(state['people'][0]), amount=3, unit='工日',
                        start='2026/3/2', end='2026/3/3')
        bad = {**selected, 'end':'', 'amount':'错填', 'unit':'天'}
        result = import_preview(state, filled([selected, bad], fields=DATED_GRID_FIELDS))
        self.assertEqual([row['row'] for row in result['rows']], [2])
        row = result['errors'][0]
        self.assertEqual(row['row'], 3)
        self.assertEqual({issue['field'] for issue in row['issues']}, {'amount','unit','end'})
        self.assertEqual(row['data']['start'], '2026/3/2')
        self.assertEqual(row['data']['amount'], '错填')
        repaired = repair_import_row(state, dict(layout=result['layout'], epoch=result['epoch'], row=3,
            data={**row['data'], 'end':'2026/3/5','amount':'4','unit':'工日'}))
        self.assertEqual(repaired['errors'], [])
        self.assertEqual(repaired['rows'][0]['data']['end'], '2026-03-05')
        self.assertEqual(repaired['rows'][0]['person_id'], state['people'][0]['id'])
        self.assertEqual(state, before)
    def test_identity_matching_and_conflicts(self):
        s=empty_state();s['people']=[dict(id='person',name=BASE['name'],company=BASE['company'],code='001')]
        r=import_preview(s,filled([BASE]));self.assertEqual(r['rows'][0]['person_id'],'person')
        r=import_preview(s,filled([{**BASE,'name':'同号异人'}]));self.assertTrue(r['errors'])
        r=import_preview(s,filled([{**BASE,'company':'另一单位'}]));self.assertFalse(r['errors']);self.assertIsNone(r['rows'][0]['person_id'])
        r=import_preview(empty_state(),filled([BASE,{**BASE,'title':'不一致'}]));self.assertEqual(r['errors'][0]['row'],3)

class ExportTests(unittest.TestCase):
    def setUp(self): self.s=demo_state()
    def csv(self,pids,person=None): return list(csv.reader(io.StringIO(scoped_report(self.s,7,pids,person).decode('utf-8-sig'))))
    def test_scope_keeps_full_cross_project_context(self):
        rows=self.csv(['p1'],'u1')
        header=next(i for i,row in enumerate(rows) if row and row[0]=='人员' and '申报ID' in row)
        detail=[]
        for row in rows[header+1:]:
            if not row: break
            detail.append(row)
        self.assertEqual(len(detail),1);self.assertEqual(detail[0][5],'e1');self.assertEqual(detail[0][8],'18')
        self.assertTrue(any('e1、e2、e3' in row for row in rows))
    def test_money_unit_mismatch_does_not_invent_zero(self):
        e=self.s['entries'][0];e.update(price=100,price_unit='工时',basis_price=90,basis_unit='工日')
        row=next(row for row in self.csv(['p1'],'u1') if len(row)>5 and row[5]=='e1')
        self.assertIn('单位不同',row[15]);self.assertIn('待补',row[19])
    def test_money_differences_are_not_deductions(self):
        self.s['entries'][0].update(price=100,basis_price=90,price_unit='工日',basis_unit='工日')
        row=next(row for row in self.csv(['p1'],'u1') if len(row)>5 and row[5]=='e1')
        self.assertEqual(row[15],'1800');self.assertEqual(row[18],'1620');self.assertEqual(row[19],'180')
    def test_default_projects_and_no_problem_person(self):
        self.assertTrue(all(p['problem'] for p in export_options(self.s,'u1')['projects']))
        self.assertFalse(any(p['problem'] for p in export_options(self.s,'u2')['projects']))
    def test_invalid_scope_rejected(self):
        for ids,person in [([],None),(['bogus'],None),(['p1'],'bogus')]:
            with self.assertRaises(ValueError): scoped_report(self.s,0,ids,person)
    def test_csv_formula_safety_and_excluded(self):
        self.s['people'][0]['name']='=danger'
        self.s['entries'][0].update(duplicate='duplicate',status='pending')
        row=next(row for row in self.csv(['p1'],'u1') if len(row)>5 and row[5]=='e1')
        self.assertEqual(row[0],"'=danger");self.assertIn('不计入',row[11]);self.assertEqual(row[12],'不参与核查')
    def test_atomic_revision_checked_save_of_project_people_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'ledger.sqlite3');rev,state=store.read();before=copy.deepcopy(state)
            state['projects'].append(dict(id='p',code='P',name='项目'))
            state['people'].append(dict(id='u',name='人',company='单位',code='U'))
            state['entries'].append(dict(id='e',person_id='u',project_id='p',amount=1,unit='工日',duplicate='pending',status='pending'))
            bad=copy.deepcopy(state);bad['entries'][0]['person_id']='missing'
            with self.assertRaises(ValueError):store.save(bad,rev,'测试','批量录入')
            self.assertEqual(store.read(),(rev,before))
            store.save(state,rev,'测试','批量录入')
            with self.assertRaises(Conflict): store.save(state,rev,'测试','重复提交')
            self.assertEqual(len(store.history()),2)

class WorkflowHttpTests(unittest.TestCase):
    def test_preview_export_and_template_routes_preserve_both_ledgers(self):
        with tempfile.TemporaryDirectory() as folder:
            stores={False:Store(Path(folder)/'real.sqlite3'),True:Store(Path(folder)/'demo.sqlite3',True)}
            before={k:s.read() for k,s in stores.items()}
            server=ThreadingHTTPServer(('127.0.0.1',0),handler_factory(stores))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                req=urllib.request.Request(base+'/api/demo/import-preview',data=json.dumps({'file':filled([BASE])}).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response: self.assertEqual(len(json.load(response)['rows']),1)
                with urllib.request.urlopen(base+'/api/demo/export-options?person=u1') as response: self.assertEqual(len(json.load(response)['projects']),3)
                with urllib.request.urlopen(base+'/api/demo/template') as response:
                    with ZipFile(io.BytesIO(response.read())) as z:
                        demo_main=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                        self.assertIn(person_choice(before[True][1]['people'][0]),''.join(ET.fromstring(z.read('xl/worksheets/sheet2.xml')).itertext()))
                with urllib.request.urlopen(base+'/api/template') as response:
                    with ZipFile(io.BytesIO(response.read())) as z:
                        actual_main=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                        for ref in ('F2','L2','M2'):
                            self.assertEqual(actual_main.find(f'.//s:c[@r="{ref}"]/s:f',NS).text,
                                             demo_main.find(f'.//s:c[@r="{ref}"]/s:f',NS).text)
                        self.assertEqual(ET.tostring(actual_main.find('s:sheetData/s:row',NS)),
                                         ET.tostring(demo_main.find('s:sheetData/s:row',NS)))
                        self.assertNotIn(before[True][1]['people'][0]['name'],z.read('xl/worksheets/sheet2.xml').decode())
                request_data=dict(file=filled([dict(person_choice=person_choice(before[True][1]['people'][0]),amount=2)],fields=COMPACT_FIELDS),defaults=dict(start='2026/3/2',end='2026/3/6',unit='工日'))
                req=urllib.request.Request(base+'/api/demo/template-refresh',data=json.dumps({'file':request_data['file']}).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:
                    self.assertIn('attachment',response.headers['Content-Disposition'])
                    refreshed=response.read()
                with ZipFile(io.BytesIO(refreshed)) as z:
                    self.assertIn(person_choice(before[True][1]['people'][0]),''.join(ET.fromstring(z.read('xl/worksheets/sheet2.xml')).itertext()))
                encoded=base64.b64encode(refreshed).decode()
                self.assertEqual(read_xlsx(request_data['file']),read_xlsx(encoded))
                request_data['file']=encoded
                req=urllib.request.Request(base+'/api/demo/import-preview',data=json.dumps(request_data).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:
                    parsed=json.load(response);self.assertEqual(parsed['errors'],[]);self.assertEqual(parsed['rows'][0]['data']['amount'],2)
                    self.assertEqual(parsed['rows'][0]['data']['start'],'2026-03-02')
                with urllib.request.urlopen(base+'/api/demo/export-scoped?project=p1&person=u1') as response:
                    self.assertIn('attachment',response.headers['Content-Disposition']); self.assertIn('林明远',response.read().decode('utf-8-sig'))
                with urllib.request.urlopen(base+'/project-hours-template.xlsx') as response: self.assertTrue(response.read().startswith(b'PK'))
                self.assertEqual({k:s.read() for k,s in stores.items()},before)
            finally: server.shutdown();server.server_close();thread.join()
