import copy
import json
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from calendar_io import bundled_calendars, calendar_package, fetch_intranet_calendar
from engine import Capacity, DEFAULT_CONFIG, review_person
from sample_data import demo_state
from server import Store, Conflict, handler_factory
from calendar_sync import sync_calendar


class CalendarTests(unittest.TestCase):
    def test_background_weekly_sync_and_retry_preserve_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'ledger.sqlite3')
            revision, state = store.read()
            state['calendar_update'] = {'url': 'http://127.0.0.1/calendar', 'automatic': True}
            store.save(state, revision, '测试', '启用日历自动同步')
            package = bundled_calendars()
            now = datetime(2026, 11, 19, tzinfo=timezone.utc)
            with patch('calendar_sync.fetch_intranet_calendar'):
                # Inject explicitly so tests make no network requests.
                calls = []
                def fetch(url):
                    calls.append(url)
                    return package
                sync_calendar(store, Conflict, now, fetch)
                saved = store.read()
                self.assertEqual(saved[1]['calendars'], package['calendars'])
                self.assertEqual(saved[1]['people'], [])
                self.assertEqual(saved[1]['projects'], [])
                self.assertEqual(store.calendar_status()['changed_years'], [2024, 2025, 2026, 2027])
                sync_calendar(store, Conflict, now + timedelta(days=6), fetch)
                self.assertEqual(len(calls), 1)
                sync_calendar(store, Conflict, now + timedelta(days=7), fetch)
                self.assertEqual(len(calls), 2)
                self.assertEqual(store.read(), saved)
                def failure(url):
                    calls.append(url)
                    raise ValueError('连接超时')
                sync_calendar(store, Conflict, now + timedelta(days=14), failure)
                self.assertEqual(store.read(), saved)
                self.assertEqual(store.calendar_status()['error'], '连接超时')
                sync_calendar(store, Conflict, now + timedelta(days=14, minutes=59), failure)
                self.assertEqual(len(calls), 3)
                sync_calendar(store, Conflict, now + timedelta(days=14, hours=1), fetch)
                self.assertEqual(len(calls), 4)
                self.assertFalse(store.calendar_status()['error'])

    def test_background_sync_respects_source_changes_and_concurrent_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / 'ledger.sqlite3')
            revision, state = store.read()
            state['calendar_update'] = {'url': 'http://127.0.0.1/calendar', 'automatic': True}
            store.save(state, revision, '测试', '启用自动同步')
            now = datetime(2026, 11, 19, tzinfo=timezone.utc)
            def concurrent_edit(url):
                revision, state = store.read()
                state['projects'].append({'id': 'manual-project', 'code': 'P01', 'name': '同时新增的项目'})
                store.save(state, revision, '测试', '新增项目')
                return bundled_calendars()
            sync_calendar(store, Conflict, now, concurrent_edit)
            self.assertEqual(store.read()[1]['projects'][0]['id'], 'manual-project')
            def disable_source(url):
                revision, state = store.read()
                state['calendar_update']['automatic'] = False
                store.save(state, revision, '测试', '关闭自动同步')
                package = bundled_calendars()
                package['calendars'][0]['source'] = '不应写入的旧请求'
                return package
            sync_calendar(store, Conflict, now + timedelta(days=7), disable_source)
            self.assertNotEqual(store.read()[1]['calendars'][0]['source'], '不应写入的旧请求')
            fetch = unittest.mock.Mock()
            sync_calendar(store, Conflict, now + timedelta(days=14), fetch)
            fetch.assert_not_called()

    def test_intranet_fetch_rejects_external_and_mixed_dns(self):
        for url in ('file:///etc/hosts', 'http://user:password@127.0.0.1/calendar', 'http://127.0.0.1/calendar#fragment', ''):
            with self.assertRaises(ValueError):
                fetch_intranet_calendar(url)
        for addresses in [
            [(2, 1, 6, '', ('8.8.8.8', 80))],
            [(2, 1, 6, '', ('10.0.0.2', 80)), (2, 1, 6, '', ('8.8.8.8', 80))],
        ]:
            with patch('calendar_io.socket.getaddrinfo', return_value=addresses):
                with self.assertRaisesRegex(ValueError, '仅支持内网'):
                    fetch_intranet_calendar('http://calendar.internal/api/calendar-feed')

    def test_intranet_service_bad_response_and_timeout(self):
        class Service(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', 'https://example.com/calendar')
                    self.end_headers()
                    return
                self.send_response(200)
                if self.path == '/large':
                    self.send_header('Content-Length', '1000001')
                self.end_headers()
                self.wfile.write(b'<html>calendar</html>')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            for path, message in [('/redirect', '跳转'), ('/large', '超过'), ('/html', '有效的日历 JSON')]:
                with self.assertRaisesRegex(ValueError, message):
                    fetch_intranet_calendar(base + path)
            with patch('calendar_io.http.client.HTTPConnection.request', side_effect=TimeoutError()):
                with self.assertRaisesRegex(ValueError, '连接超时'):
                    fetch_intranet_calendar(base + '/calendar')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_official_bundle_and_holiday_capacity(self):
        package = bundled_calendars()
        calendars = package['calendars']
        self.assertEqual([c['year'] for c in calendars], [2024, 2025, 2026, 2027])
        for start, end, expected in [
            ('2024-02-09', '2024-02-09', 1),
            ('2025-01-28', '2025-02-04', 0),
            ('2026-02-14', '2026-02-23', 1),
            ('2026-05-01', '2026-05-09', 4),
            ('2027-02-05', '2027-02-14', 1),
            ('2026-12-31', '2027-01-03', 1),
        ]:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            self.assertEqual(Capacity(first, last, DEFAULT_CONFIG, calendars).get(first, last)[1], expected, start)

    def test_import_validation_rejects_incomplete_or_conflicting_packages(self):
        package = bundled_calendars()
        for mutate in [
            lambda p: p.update(version=2),
            lambda p: p.update(calendars=[]),
            lambda p: p['calendars'].append(p['calendars'][0]),
            lambda p: p['calendars'][0].update(source=''),
            lambda p: p['calendars'][0].update(holidays=['2024-02-30']),
            lambda p: p['calendars'][0].update(makeup_days=['2024-01-01']),
            lambda p: p['calendars'][0].update(holidays=['2025-01-01']),
            lambda p: p['calendars'][0].update(holidays=['2024-01-01', '2024-01-01']),
        ]:
            candidate = copy.deepcopy(package)
            mutate(candidate)
            with self.assertRaises(ValueError):
                calendar_package(candidate)
        self.assertEqual(bundled_calendars(), package)

    def test_missing_calendar_is_reported_outside_the_worst_window(self):
        state = demo_state()
        person = state['people'][0]
        entries = [e for e in state['entries'] if e['person_id'] == person['id']]
        state['entries'] = entries[:2]
        state['calendars'] = bundled_calendars()['calendars']
        state['entries'][0].update(start='2026-03-02', end='2026-03-03', amount=1000, unit='工日')
        state['entries'][1].update(start='2028-03-01', end='2028-03-02', amount=1, unit='工日')
        result = review_person(person, state)
        self.assertEqual(result['worst']['missing_calendar'], [])
        self.assertTrue(any('2028年日历未维护' in f['message'] for f in result['findings']))

    def test_calendar_endpoints_are_read_only_and_save_is_revision_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            stores = {demo: Store(Path(folder) / (str(demo) + '.sqlite3'), demo) for demo in (False, True)}
            before = {key: store.read() for key, store in stores.items()}
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(stores))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base + '/api/calendar-bundle') as response:
                    package = json.load(response)
                request = urllib.request.Request(base + '/api/demo/calendar-preview', data=json.dumps(package).encode(),
                                                 headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(len(json.load(response)['calendars']), 4)
                self.assertEqual({key: store.read() for key, store in stores.items()}, before)
                revision, state = before[False]
                state['calendars'] = package['calendars']
                stores[False].save(state, revision, '日历测试', '导入年度日历')
                self.assertEqual(stores[False].read()[1]['calendars'], package['calendars'])
                self.assertEqual(stores[True].read(), before[True])
                self.assertIn('导入年度日历', str(stores[False].history()))
                new_before = {key: store.read() for key, store in stores.items()}
                request = urllib.request.Request(base + '/api/demo/calendar-sync',
                    data=json.dumps({'url': base + '/api/calendar-feed'}).encode(),
                    headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request) as response:
                    synced = json.load(response)
                self.assertEqual(synced['calendars'], package['calendars'])
                self.assertEqual(synced['fetched_from'], base + '/api/calendar-feed')
                self.assertIn('fetched_at', synced)
                self.assertEqual({key: store.read() for key, store in stores.items()}, new_before)
                revision, state = stores[False].read()
                state['calendar_update'] = {'url': base + '/api/calendar-feed'}
                stores[False].save(state, revision, '日历测试', '保存内网更新地址')
                self.assertEqual(stores[False].read()[1]['calendar_update']['url'], base + '/api/calendar-feed')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
