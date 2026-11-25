import unittest
from copy import deepcopy
from io import BytesIO

try:
    from review_pdf import overview_pdf, report_assessments, review_pdf
except ModuleNotFoundError as exc:
    if exc.name != 'reportlab':
        raise
    raise unittest.SkipTest('PDF export requires ReportLab')

from sample_data import demo_state


class PdfSummaryTests(unittest.TestCase):
    def setUp(self):
        self.state = demo_state()

    def assessment(self, person='u2', projects=('p1',)):
        return report_assessments(self.state, projects, person)[0]

    def test_project_and_ledger_have_independent_capacity_results(self):
        result = self.assessment('u1')
        self.assertEqual(max(w['rank'] for w in result['local_windows']), 0)
        self.assertEqual(max(w['rank'] for w in result['full']['windows']), 3)
        self.assertEqual(result['status'], 'review')

    def test_multiple_claims_in_one_project_are_added_before_comparing(self):
        first = next(e for e in self.state['entries'] if e['id'] == 'e4')
        first.update(start='2026-03-02', end='2026-03-13', amount=8)
        self.state['entries'].append({**first, 'id': 'additional-claim', 'duplicate': 'append'})
        result = self.assessment()
        window = max(result['local_windows'], key=lambda w: w['rank'])
        self.assertEqual(window['demand'], 16)
        self.assertEqual(set(window['entry_ids']), {'e4', 'additional-claim'})
        self.assertGreater(window['rank'], 0)

    def test_unselected_project_only_overload_is_in_ledger_result(self):
        remote = next(e for e in self.state['entries'] if e['id'] == 'e5')
        remote.update(start='2026-04-06', end='2026-04-10', amount=20)
        result = self.assessment()
        self.assertTrue(any(w['entry_ids'] == ['e5'] and w['rank'] > 0 for w in result['full']['windows']))
        self.assertTrue(all('e5' not in w['entry_ids'] for w in result['local_windows']))
        self.assertEqual(result['status'], 'review')

    def test_missing_calendar_cannot_pass(self):
        self.state['calendars'] = []
        self.assertEqual(self.assessment()['status'], 'pending')

    def test_unknown_conversion_and_partial_dates_cannot_pass(self):
        self.assertEqual(self.assessment('u6', ('p4',))['status'], 'pending')
        first = next(e for e in self.state['entries'] if e['id'] == 'e4')
        first['start'] = ''
        self.assertEqual(self.assessment()['status'], 'pending')

    def test_pending_duplicate_cannot_pass(self):
        first = next(e for e in self.state['entries'] if e['id'] == 'e4')
        first.update(amount=1, duplicate='pending')
        self.state['entries'].append({**first, 'id': 'uncertain-claim'})
        self.assertEqual(self.assessment()['status'], 'pending')

    def test_excluded_export_is_not_a_pass(self):
        first = next(e for e in self.state['entries'] if e['id'] == 'e4')
        first['duplicate'] = 'duplicate'
        self.assertEqual(self.assessment()['status'], 'excluded')

    def test_complete_normal_person_passes_and_assessment_does_not_mutate_state(self):
        before = deepcopy(self.state)
        self.assertEqual(self.assessment()['status'], 'pass')
        self.assertEqual(self.state, before)

    def test_report_opens_with_conclusion_and_explains_unselected_anomaly(self):
        from pypdf import PdfReader
        remote = next(e for e in self.state['entries'] if e['id'] == 'e5')
        remote.update(start='2026-04-06', end='2026-04-10', amount=20)
        pages = PdfReader(BytesIO(review_pdf(self.state, 7, ['p1'], 'u2', demo=True))).pages
        first_page = ''.join(pages[0].extract_text().split())
        all_text = ''.join(''.join(p.extract_text().split()) for p in pages)
        self.assertIn('核查结论（模拟）', first_page)
        self.assertIn('发现问题，需核查', first_page)
        self.assertIn('全库工时超参考', first_page)
        self.assertIn('工程数据治理（DEMO-02）', all_text)
        self.assertIn('2026-04-06至2026-04-10', all_text)

    def test_unknown_conversion_is_shown_as_not_yet_counted(self):
        from pypdf import PdfReader
        pages = PdfReader(BytesIO(review_pdf(self.state, 7, ['p4'], 'u6', demo=True))).pages
        text = ''.join(''.join(p.extract_text().split()) for p in pages)
        self.assertIn('资料待补，暂无法判断是否合格', text)
        self.assertIn('暂未计入工时', text)
        self.assertNotIn('核查通过（模拟）', text)

    def test_approved_template_names_projects_dates_and_excess_together(self):
        from pypdf import PdfReader
        pages=PdfReader(BytesIO(review_pdf(self.state,7,['p1','p2','p3'],'u1',demo=True))).pages
        text=''.join(''.join(p.extract_text().split()) for p in pages)
        self.assertIn('各项目单独看',text)
        self.assertIn('管网巡检数字化（投入2026-03-02至2026-03-27）',text)
        self.assertIn('全库累计需要核查的时段',text)
        self.assertIn('超出11工日',text)
        self.assertIn('待核实',text)
        self.assertNotIn('人月',text)
        self.assertNotIn('高负荷',text)

    def test_overview_includes_people_without_claims_and_empty_ledgers(self):
        from pypdf import PdfReader
        from engine import empty_state
        self.state['people'].append(dict(id='no-claims',name='尚未申报人员',code='NEW',company='新单位'))
        pdf=PdfReader(BytesIO(overview_pdf(self.state,8,demo=True)))
        text=''.join(p.extract_text() for p in pdf.pages)
        self.assertIn('尚未申报人员',text)
        self.assertIn('暂无有效申报',text)
        empty=PdfReader(BytesIO(overview_pdf(empty_state(),0)))
        self.assertEqual(len(empty.pages),1)
        self.assertIn('当前台账暂无人员记录',empty.pages[0].extract_text())

    def test_four_risk_names_keep_their_colors_in_exported_reports(self):
        import pdfplumber
        expected = {'低风险': (35/255, 118/255, 77/255), '中风险': (138/255, 101/255, 13/255),
                    '高风险': (180/255, 35/255, 24/255), '极高风险': (123/255, 44/255, 191/255)}
        with pdfplumber.open(BytesIO(overview_pdf(self.state, 8, demo=True))) as pdf:
            for label, color in expected.items():
                expression = '(?<!极)高风险' if label == '高风险' else label
                matches = [match for page in pdf.pages for match in page.search(expression, return_chars=True)]
                self.assertTrue(matches, label)
                for match in matches:
                    self.assertTrue(all(all(abs(actual - target) < .01 for actual, target in zip(char['non_stroking_color'], color))
                                        for char in match['chars']), label)

    def test_project_periods_remain_separate_and_untrusted_names_are_escaped(self):
        from pypdf import PdfReader
        first=next(e for e in self.state['entries'] if e['id']=='e4')
        self.state['entries'].append({**first,'id':'second-period','start':'2026-04-20','end':'2026-04-24','amount':1})
        self.state['projects'][0]['name']='项目 <研发&测试>'
        pages=PdfReader(BytesIO(review_pdf(self.state,7,['p1'],'u2'))).pages
        text=''.join(''.join(p.extract_text().split()) for p in pages)
        self.assertIn('项目<研发&测试>',text)
        self.assertIn('投入2026-03-02至2026-03-27；2026-04-20至2026-04-24',text)

    def test_only_overload_problem_text_is_red_and_verification_notes_are_black(self):
        import pdfplumber
        document=BytesIO(review_pdf(self.state,7,['p4']))
        def red(char):
            color=char.get('non_stroking_color')
            return isinstance(color,tuple) and len(color)==3 and color[0]>.65 and color[1]<.2 and color[2]<.2
        with pdfplumber.open(document) as pdf:
            labels=[match for page in pdf.pages for match in page.search('投入日期需核对',return_chars=True)]
            self.assertTrue(labels)
            self.assertTrue(all(not red(c) for match in labels for c in match['chars']))
            pages=[page for page in pdf.pages if page.search('待核实')]
            self.assertTrue(pages)
            for page in pages:
                title=page.search('待核实')[0]
                chars=[c for c in page.chars if c['top']>title['bottom'] and c['bottom']<page.height-43]
                self.assertTrue(all(not red(c) for c in chars))

    def test_outside_period_explains_exact_dates_without_deduction(self):
        from engine import analyze
        entry=next(e for e in self.state['entries'] if e['id']=='e4')
        entry.update(start='2026-02-25',end='2026-05-02')
        result=next(r for r in analyze(self.state) if r['person']['id']=='u2')
        finding=next(f for f in result['findings'] if f['entry_id']=='e4' and '之外' in f['message'])
        self.assertIn('管网巡检数字化',finding['detail'])
        self.assertIn('2026-02-25至2026-02-28',finding['detail'])
        self.assertIn('2026-05-01至2026-05-02',finding['detail'])
        self.assertIn('不能按越界天数推算审减量',finding['detail'])


class PdfHttpTests(unittest.TestCase):
    def test_all_pdf_routes_preserve_ledgers_and_csv(self):
        import json
        from pathlib import Path
        import tempfile
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        from pypdf import PdfReader
        from server import Store, handler_factory
        with tempfile.TemporaryDirectory() as directory:
            stores={False:Store(Path(directory)/'ledger.sqlite3'),True:Store(Path(directory)/'demo.sqlite3',True)}
            before={key:store.read() for key,store in stores.items()}
            http=ThreadingHTTPServer(('127.0.0.1',0),handler_factory(stores))
            thread=threading.Thread(target=http.serve_forever,daemon=True)
            thread.start()
            base=f'http://127.0.0.1:{http.server_port}'
            try:
                for route,title in [('/api/export?format=pdf','人员核查结果总表'),
                                    ('/api/demo/export?format=pdf','人员核查结果总表'),
                                    ('/api/demo/export-scoped?project=p1&format=pdf','项目工时核查报告'),
                                    ('/api/demo/export-scoped?project=p1&person=u1&format=pdf','人员工时核查报告')]:
                    with urllib.request.urlopen(base+route) as response:
                        self.assertEqual(response.headers.get_content_type(),'application/pdf')
                        self.assertIn('attachment',response.headers['Content-Disposition'])
                        pdf=PdfReader(BytesIO(response.read()))
                        self.assertIn(title,pdf.pages[0].extract_text())
                for route in ('/api/demo/export','/api/demo/export-scoped?project=p1&person=u1'):
                    with urllib.request.urlopen(base+route) as response:
                        self.assertEqual(response.headers.get_content_type(),'text/csv')
                        self.assertIn('林明远',response.read().decode('utf-8-sig'))
                self.assertEqual({key:store.read() for key,store in stores.items()},before)
            finally:
                http.shutdown()
                http.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
