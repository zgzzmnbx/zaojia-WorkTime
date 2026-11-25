import base64, copy, tempfile, unittest
from pathlib import Path
from engine import empty_state, review_person, validate
from sample_data import demo_state
from server import Store

CID='d0277732-6a3d-4d04-88c1-2cc58c6e4101'
PNG='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l2sAAAAASUVORK5CYII='
IMAGE=dict(id=CID,mime='image/png',name='证书.png',data=PNG)

def profile():
    return dict(id='new-person',name='测试人员',code='CERT-01',company='',title='技术专家',title_permanent=True,qualification_required=True,certificate_id=CID)

class QualificationTests(unittest.TestCase):
    def test_permanent_requires_no_expiry_and_respects_acquisition(self):
        state=demo_state();person=state['people'][0]
        person.update(title_permanent=True,title_from='',title_to='',title_source='',certificate_id=CID)
        self.assertFalse(any('证明依据或有效期不完整' in f['message'] for f in review_person(person,state)['findings']))
        person['title_from']='2026-04-01'
        self.assertTrue(any('有效期未覆盖' in f['message'] for f in review_person(person,state)['findings']))

    def test_new_person_requires_level_and_certificate(self):
        state=empty_state();state['people']=[profile()];validate(state)
        for invalid in [dict(certificate_id=''),dict(title='未知级别'),dict(title_permanent=False)]:
            bad=copy.deepcopy(state);bad['people'][0].update(invalid)
            with self.assertRaises(ValueError):validate(bad)

    def test_omitted_company_requires_unambiguous_code(self):
        state=empty_state();state['people']=[profile(),dict(profile(),id='other',company='某单位')]
        with self.assertRaisesRegex(ValueError,'工号已存在'):validate(state)
        state['people'][0]['company']='另一单位';validate(state)

    def test_company_required_for_new_or_edited_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'ledger.sqlite3')
            state = empty_state()
            state['people'] = [dict(profile(), company='  ')]
            with self.assertRaisesRegex(ValueError, '所属单位必填'):
                store.save(state, 0, '测试', '新增人员', certificates=[IMAGE])
            store.save(state, 0, '测试', '恢复旧资料', True, [IMAGE])
            store.save(state, 1, '测试', '保留旧资料')
            state['people'][0]['name'] = '更正姓名'
            with self.assertRaisesRegex(ValueError, '所属单位必填'):
                store.save(state, 2, '测试', '更正资料')
            state['people'][0]['company'] = '测试单位'
            store.save(state, 2, '测试', '补齐单位')

    def test_image_commit_backup_restore_and_history(self):
        with tempfile.TemporaryDirectory() as folder:
            first=Store(Path(folder)/'first.sqlite3');second=Store(Path(folder)/'second.sqlite3')
            state=empty_state();state['people']=[dict(profile(), company='测试单位')]
            with self.assertRaisesRegex(ValueError,'找不到人员资格证'):first.save(state,0,'测试','人员入库')
            with self.assertRaisesRegex(ValueError,'JPG'):
                first.save(state,0,'测试','无效图片',certificates=[dict(IMAGE,mime='image/svg+xml')])
            self.assertIsNone(first.certificate(CID));self.assertEqual(first.read()[0],0)
            first.save(state,0,'测试','人员入库',certificates=[IMAGE]);backup=first.backup()
            self.assertEqual(backup['certificates'],[IMAGE]);self.assertIsNone(second.certificate(CID))
            second.save(backup['state'],0,'测试','恢复',True,backup['certificates'])
            self.assertEqual(second.certificate(CID)[2],base64.b64decode(PNG))
            first.save(empty_state(),1,'测试','恢复空台账',True)
            self.assertEqual(first.revision(1)['people'][0]['certificate_id'],CID)
            self.assertIsNotNone(first.certificate(CID))
