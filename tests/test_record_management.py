import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from engine import LABELS, analyze, validate
from server import Conflict, Store, handler_factory
from test_qualifications import IMAGE, CID, profile


class RecordManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'demo.sqlite3', True)

    def tearDown(self):
        self.temp.cleanup()

    def test_project_delete_removes_only_related_claims_and_restore_recalculates(self):
        revision, original = self.store.read()
        before = {e['id'] for e in original['entries'] if e['project_id'] == 'p1'}
        self.store.delete_record('projects', 'p1', revision, '测试')
        revision, removed = self.store.read()
        self.assertFalse(any(p['id'] == 'p1' for p in removed['projects']))
        self.assertEqual(removed['people'], original['people'])
        self.assertEqual({e['id'] for e in removed['entries']}, {e['id'] for e in original['entries']} - before)
        self.assertEqual({e['id'] for e in removed['deleted_records'][0]['entries']}, before)
        validate(removed)
        self.assertNotEqual(analyze(removed), analyze(original))
        self.store.restore_record(removed['deleted_records'][0]['id'], revision, '恢复测试')
        _, restored = self.store.read()
        self.assertEqual(sorted(restored['entries'], key=lambda e: e['id']), sorted(original['entries'], key=lambda e: e['id']))
        self.assertEqual(analyze(restored), analyze(original))
        self.assertEqual(restored['deleted_records'], [])
        self.assertIn('恢复项目', self.store.history()[0]['action'])
        self.assertIn('删除项目', self.store.history()[1]['action'])
        self.assertEqual(self.store.revision(0), original)

    def test_person_delete_keeps_projects_and_other_people(self):
        revision, original = self.store.read()
        self.store.delete_record('people', 'u1', revision, '测试')
        revision, state = self.store.read()
        self.assertEqual(state['projects'], original['projects'])
        self.assertEqual(state['people'], [p for p in original['people'] if p['id'] != 'u1'])
        self.assertEqual(state['entries'], [e for e in original['entries'] if e['person_id'] != 'u1'])
        self.assertFalse(any(r['person']['id'] == 'u1' for r in analyze(state)))
        self.store.restore_record(state['deleted_records'][0]['id'], revision, '测试')
        self.assertEqual({r['person']['id'] for r in analyze(self.store.read()[1])}, {p['id'] for p in original['people']})

    def test_single_claim_delete_preserves_siblings_including_confirmed_append(self):
        revision, original = self.store.read()
        self.store.delete_record('entries', 'e1', revision, '测试')
        revision, state = self.store.read()
        self.assertEqual(state['people'], original['people'])
        self.assertEqual(state['projects'], original['projects'])
        self.assertEqual(state['entries'], [e for e in original['entries'] if e['id'] != 'e1'])
        self.store.restore_record(state['deleted_records'][0]['id'], revision, '测试')
        self.assertEqual(len(self.store.read()[1]['entries']), len(original['entries']))

    def test_missing_records_and_stale_revisions_never_change_current_state(self):
        before = self.store.read()
        for kind, identity in [('projects', 'missing'), ('people', 'missing'), ('invalid', 'u1')]:
            with self.assertRaises(ValueError):
                self.store.delete_record(kind, identity, before[0], '测试')
            self.assertEqual(self.store.read(), before)
        with self.assertRaises(Conflict):
            self.store.delete_record('people', 'u1', 100, '测试')
        with self.assertRaises(ValueError):
            self.store.delete_record('people', 'u1', 0, ' ')
        self.assertEqual(self.store.read(), before)
        self.store.delete_record('people', 'u1', 0, '测试')
        revision, state = self.store.read()
        with self.assertRaises(Conflict):
            self.store.restore_record(state['deleted_records'][0]['id'], 0, '测试')
        self.assertEqual(self.store.read(), (revision, state))

    def test_restore_missing_dependency_then_parent_and_no_double_restore(self):
        self.store.delete_record('projects', 'p1', 0, '测试')
        project_deleted = self.store.read()[1]['deleted_records'][0]['id']
        self.store.delete_record('people', 'u1', 1, '测试')
        revision, before = self.store.read()
        person_deleted = before['deleted_records'][0]['id']
        with self.assertRaisesRegex(ValueError, '先恢复关联人员'):
            self.store.restore_record(project_deleted, revision, '测试')
        self.assertEqual(self.store.read(), (revision, before))
        self.store.restore_record(person_deleted, revision, '测试')
        self.store.restore_record(project_deleted, revision + 1, '测试')
        with self.assertRaisesRegex(ValueError, '可能已恢复'):
            self.store.restore_record(project_deleted, revision + 2, '测试')
        self.assertEqual(self.store.read()[1]['deleted_records'], [])

    def test_restore_identity_conflict_is_atomic(self):
        self.store.delete_record('people', 'u1', 0, '测试')
        revision, state = self.store.read()
        deleted_id = state['deleted_records'][0]['id']
        person = copy.deepcopy(state['deleted_records'][0]['record'])
        person['id'] = 'different-person'
        state['people'].append(person)
        self.store.save(state, revision, '测试', '同工号重新入库')
        before = self.store.read()
        with self.assertRaisesRegex(ValueError, '工号重复'):
            self.store.restore_record(deleted_id, before[0], '测试')
        self.assertEqual(self.store.read(), before)

    def test_deleted_certificates_survive_backup_to_another_database(self):
        revision, state = self.store.read()
        state['people'].append(dict(profile(), company='测试单位'))
        self.store.save(state, revision, '测试', '新增证书', certificates=[IMAGE])
        self.store.delete_record('people', 'new-person', revision + 1, '测试')
        backup = self.store.backup()
        self.assertEqual(backup['certificates'], [IMAGE])
        other = Store(Path(self.temp.name) / 'other.sqlite3')
        other.save(backup['state'], 0, '测试', '恢复备份', True, backup['certificates'])
        identity = backup['state']['deleted_records'][0]['id']
        other.restore_record(identity, 1, '测试')
        person = next(p for p in other.read()[1]['people'] if p['id'] == 'new-person')
        self.assertEqual(person['certificate_id'], CID)
        self.assertIsNotNone(other.certificate(CID))

    def test_restoring_legacy_claim_does_not_rewrite_its_original_unit(self):
        revision, state = self.store.read()
        entry = state['entries'][0]
        entry['unit'] = '人月'
        self.store.save(state, revision, '测试', '恢复旧格式备份', restore=True)
        self.store.delete_record('entries', entry['id'], revision + 1, '测试')
        revision, removed = self.store.read()
        self.store.restore_record(removed['deleted_records'][0]['id'], revision, '测试')
        restored = next(e for e in self.store.read()[1]['entries'] if e['id'] == entry['id'])
        self.assertEqual(restored, entry)

    def test_risk_names_match_the_existing_rank_order(self):
        self.assertEqual(LABELS, ['低风险', '中风险', '高风险', '极高风险'])
        self.assertTrue(all(w['label'] == LABELS[w['rank']] for r in analyze(self.store.read()[1]) for w in r['windows']))


class RecordManagementHttpTests(unittest.TestCase):
    def test_delete_restore_are_revision_checked_and_isolated_from_real_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            stores = {demo: Store(Path(folder) / f'{demo}.sqlite3', demo) for demo in (False, True)}
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(stores))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}/api/demo'
            def post(path, payload):
                request = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as response:
                    return json.load(response)
            try:
                self.assertEqual(post('/delete-record', dict(kind='people', id='u1', revision=0, actor='测试'))['revision'], 1)
                state = stores[True].read()[1]
                identity = state['deleted_records'][0]['id']
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post('/restore-record', dict(id=identity, revision=0, actor='测试'))
                self.assertEqual(error.exception.code, 409)
                self.assertEqual(post('/restore-record', dict(id=identity, revision=1, actor='测试'))['revision'], 2)
                self.assertEqual(stores[False].read()[0], 0)
                self.assertEqual(stores[False].read()[1]['people'], [])
                self.assertEqual(len(stores[True].read()[1]['people']), 12)
            finally:
                server.shutdown();server.server_close();thread.join()
