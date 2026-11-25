"""Local application server, atomic shared SQLite state and append-only revisions."""
import argparse, base64, binascii, csv, io, json, mimetypes, sqlite3, threading, traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs
from project_io import scoped_report, export_options, import_preview, repair_import_row, export_import_problems, selection_template, refresh_template
from engine import VERSION, empty_state, validate, analyze, day
from sample_data import demo_state
from calendar_io import bundled_calendars, calendar_package, calendar_url, fetch_intranet_calendar
from calendar_sync import calendar_sync_loop
from record_management import KINDS, remove_record, restore_record, certificate_ids

ROOT=Path(__file__).resolve().parent
APP_VERSION=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']

def stamp(): return datetime.now(timezone.utc).isoformat()
def dumps(value): return json.dumps(value,ensure_ascii=False,allow_nan=False)

def certificate_upload(upload):
    mime=upload['mime']; name=upload['name']
    if not isinstance(name,str) or not name.strip() or len(name)>200: raise ValueError('资格证文件名无效')
    try: body=base64.b64decode(upload['data'],validate=True)
    except (ValueError,binascii.Error): raise ValueError('资格证图片读取失败')
    if not body or len(body)>3_000_000: raise ValueError('资格证图片须在3 MB以内')
    if not ((mime=='image/png' and body.startswith(b'\x89PNG\r\n\x1a\n') and body[12:16]==b'IHDR') or
            (mime=='image/jpeg' and body.startswith(b'\xff\xd8\xff')) or
            (mime=='image/webp' and body.startswith(b'RIFF') and body[8:12]==b'WEBP')):
        raise ValueError('资格证须为 JPG、PNG 或 WebP 图片')
    return mime,name,body

class Conflict(Exception): pass

class Store:
    def __init__(self,path,demo=False):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS current (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, at TEXT, actor TEXT, action TEXT, body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS certificates (id TEXT PRIMARY KEY, mime TEXT NOT NULL, name TEXT NOT NULL, body BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calendar_sync_status (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
            if not db.execute('SELECT 1 FROM current').fetchone():
                body=dumps(validate(demo_state() if demo else empty_state()))
                db.execute('INSERT INTO current VALUES (1,0,?)',(body,))
                db.execute('INSERT INTO history VALUES (0,?,?,?,?)',(stamp(),'系统','创建模拟台账' if demo else '创建空台账',body))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            with db: yield db
        finally: db.close()
    def read(self):
        with self.connect() as db:
            rev,body=db.execute('SELECT revision,body FROM current').fetchone()
        return rev,json.loads(body)
    def calendar_status(self):
        with self.connect() as db:
            row = db.execute('SELECT body FROM calendar_sync_status WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {}
    def save_calendar_status(self, status):
        with self.connect() as db:
            db.execute('INSERT INTO calendar_sync_status VALUES (1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                       (dumps(status),))
    def certificate(self,cert_id):
        with self.connect() as db:
            return db.execute('SELECT mime,name,body FROM certificates WHERE id=?',(cert_id,)).fetchone()
    @staticmethod
    def certificates_for(db,state):
        result=[]
        for cert_id in sorted(certificate_ids(state)):
            row=db.execute('SELECT mime,name,body FROM certificates WHERE id=?',(cert_id,)).fetchone()
            if row is None: raise ValueError('台账引用的资格证图片缺失')
            mime,name,body=row
            result.append(dict(id=cert_id,mime=mime,name=name,data=base64.b64encode(body).decode('ascii')))
        return result
    def backup(self):
        with self.connect() as db:
            db.execute('BEGIN')
            rev,body=db.execute('SELECT revision,body FROM current').fetchone(); state=json.loads(body)
            return dict(schema_version=1,revision=rev,exported_at=stamp(),state=state,certificates=self.certificates_for(db,state))
    def save(self,state,revision,actor,action,restore=False,certificates=None,recovery=False):
        validate(state)
        settings = state.get('calendar_update', {})
        if not isinstance(settings, dict) or ('automatic' in settings and type(settings['automatic']) is not bool):
            raise ValueError('日历自动同步设置无效')
        if settings.get('automatic') and (not isinstance(settings.get('url'), str) or not settings['url'].strip()):
            raise ValueError('启用自动同步前须填写日历服务地址')
        if settings.get('url'):
            calendar_url(settings['url'])
        if not isinstance(actor,str) or not actor.strip(): raise ValueError('填写本次操作人')
        if not isinstance(action,str) or not action.strip(): raise ValueError('缺少操作说明')
        body=dumps(state)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old_rev,old_body=db.execute('SELECT revision,body FROM current').fetchone()
            if old_rev!=revision: raise Conflict('台账已被其他页面修改，请刷新后重新编辑；当前输入仍保留')
            old_state = json.loads(old_body)
            if not restore and not recovery:
                previous_entries = {e['id']: e for e in old_state['entries']}
                for entry in state['entries']:
                    if entry != previous_entries.get(entry['id']):
                        if any(entry.get(k) not in ('工日', '工时', None, '') for k in ('unit', 'price_unit', 'basis_unit')):
                            raise ValueError('新增或修改申报仅支持工日和工时；请按原始资料核对单位后保存')
                project_date_keys = ('build_start', 'build_end', 'impl_start', 'impl_end')
                def dates(project):
                    return tuple(day(project[key]) if project.get(key) else None for key in project_date_keys)
                old_project_dates = {project['id']: dates(project) for project in old_state['projects']}
                for project in state['projects']:
                    current = dates(project)
                    if current == old_project_dates.get(project['id']):
                        continue
                    build_start, build_end, impl_start, impl_end = current
                    implementation_dates = [date for date in (impl_start, impl_end) if date is not None]
                    if build_start and any(date < build_start for date in implementation_dates):
                        raise ValueError('实施日期不能早于建设开始日期')
                    if build_end and any(date > build_end for date in implementation_dates):
                        raise ValueError('实施日期不能晚于建设结束日期')
                old_people = {p['id']: p for p in old_state['people']}
                for person in state['people']:
                    if old_people.get(person['id']) == person:
                        continue
                    if not person.get('company', '').strip():
                        raise ValueError('人员所属单位必填')
                    if person.get('title_permanent') is False and not (person.get('title_from') and person.get('title_to')):
                        raise ValueError('非长期有效的资格证须填写有效起止日期')
            refs=certificate_ids(state)
            for upload in certificates or []:
                cert_id=upload['id']
                if cert_id not in refs: raise ValueError('资格证图片未绑定到人员')
                image=certificate_upload(upload)
                old=db.execute('SELECT mime,name,body FROM certificates WHERE id=?',(cert_id,)).fetchone()
                if old and old!=image: raise ValueError('资格证编号重复，图片不能覆盖历史证据')
                if old is None: db.execute('INSERT INTO certificates VALUES (?,?,?,?)',(cert_id,*image))
            if any(db.execute('SELECT 1 FROM certificates WHERE id=?',(cid,)).fetchone() is None for cid in refs):
                raise ValueError('找不到人员资格证图片，请重新上传或使用完整备份')
            if restore:
                target=self.path.parent/'backups'; target.mkdir(exist_ok=True)
                name=f'{self.path.stem}-before-restore-r{old_rev}-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.json'
                (target/name).write_text(dumps(dict(schema_version=1,revision=old_rev,state=old_state,certificates=self.certificates_for(db,old_state))),encoding='utf-8')
            rev=old_rev+1
            db.execute('UPDATE current SET revision=?,body=? WHERE id=1',(rev,body))
            db.execute('INSERT INTO history VALUES (?,?,?,?,?)',(rev,stamp(),actor.strip(),action.strip(),body))
        return rev
    def delete_record(self,kind,record_id,revision,actor):
        current,state=self.read()
        if type(revision) is not int or current!=revision: raise Conflict('台账已被其他页面修改，请关闭窗口并刷新后重试')
        next_state,item=remove_record(state,kind,record_id,actor)
        record=item['record']
        name=record.get('name') or record['id']
        return self.save(next_state,revision,actor,f'删除{KINDS[kind]}：{name}；移入已删除记录（含{len(item["entries"])}条关联申报）')
    def restore_record(self,deleted_id,revision,actor):
        current,state=self.read()
        if type(revision) is not int or current!=revision: raise Conflict('台账已被其他页面修改，请关闭窗口并刷新后重试')
        next_state,item=restore_record(state,deleted_id)
        record=item['record']
        name=record.get('name') or record['id']
        return self.save(next_state,revision,actor,f'恢复{KINDS[item["kind"]]}：{name}（含{len(item["entries"])}条关联申报）',recovery=True)
    def history(self):
        with self.connect() as db:
            return [dict(revision=r,at=t,actor=a,action=x) for r,t,a,x in db.execute('SELECT revision,at,actor,action FROM history ORDER BY revision DESC LIMIT 200')]
    def revision(self,rev):
        with self.connect() as db:
            row=db.execute('SELECT body FROM history WHERE revision=?',(rev,)).fetchone()
        if not row: raise ValueError('找不到历史版本')
        return json.loads(row[0])

def handler_factory(stores):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt,*args): pass
        def respond(self,status,data,content_type='application/json; charset=utf-8',filename=None):
            content=dumps(data).encode('utf-8') if content_type.startswith('application/json') else data
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'")
            if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers(); self.wfile.write(content)
        def route(self):
            path=urlsplit(self.path).path
            demo=path.startswith('/api/demo/')
            return stores[demo], path.replace('/api/demo/','/api/',1) if demo else path
        def pdf_report(self,store,projects=None,person=None):
            try:
                from review_pdf import overview_pdf, review_pdf
            except ModuleNotFoundError as exc:
                if exc.name != 'reportlab': raise
                return self.respond(503,dict(error='当前 Python 环境缺少 ReportLab，安装后可导出 PDF。'))
            revision,state=store.read()
            demo=store is stores[True]
            if projects is None:
                content=overview_pdf(state,revision,demo=demo)
                filename='personnel-review-summary.pdf'
            else:
                content=review_pdf(state,revision,projects,person,demo=demo)
                filename='person-hours-review.pdf' if person else 'project-hours-review.pdf'
            return self.respond(200,content,'application/pdf',filename)
        def do_GET(self):
            try:
                store,path=self.route()
                if path=='/api/health': return self.respond(200,dict(app='expert-hours-review',version=VERSION,app_version=APP_VERSION,rule_version=VERSION))
                if path=='/api/calendar-bundle':
                    return self.respond(200,bundled_calendars())
                if path=='/api/calendar-update-status':
                    return self.respond(200,store.calendar_status())
                if path=='/api/calendar-feed':
                    revision,state=store.read()
                    return self.respond(200,calendar_package(dict(format='expert-hours-calendars',version=1,
                        bundle_version=str(revision),calendars=state['calendars'])))
                if path=='/project-hours-template.xlsx':
                    template=ROOT/'dist'/'project-hours-template.xlsx'
                    if not template.is_file(): template=ROOT/'public'/'project-hours-template.xlsx'
                    return self.respond(200,template.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','project-hours-template.xlsx')
                if path=='/api/state':
                    rev,state=store.read()
                    return self.respond(200,dict(revision=rev,state=state,results=analyze(state),history=store.history()))
                if path=='/api/template':
                    _,state=store.read()
                    template=ROOT/'dist'/'project-hours-template.xlsx'
                    if not template.is_file(): template=ROOT/'public'/'project-hours-template.xlsx'
                    return self.respond(200,selection_template(template.read_bytes(),state),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','project-hours-template.xlsx')
                if path=='/api/export-options':
                    _,state=store.read(); query=parse_qs(urlsplit(self.path).query)
                    return self.respond(200,export_options(state,query.get('person',[''])[0]))
                if path=='/api/export-scoped':
                    query=parse_qs(urlsplit(self.path).query)
                    projects=query.get('project',[])
                    person=query.get('person',[None])[0]
                    if query.get('format')==['pdf']:
                        return self.pdf_report(store,projects,person)
                    rev,state=store.read()
                    content=scoped_report(state,rev,projects,person)
                    return self.respond(200,content,'text/csv; charset=utf-8','expert-hours-detail.csv')
                if path=='/api/backup':
                    return self.respond(200,dict(**store.backup(),history=store.history()),filename='expert-hours-backup.json')
                if path.startswith('/api/certificate/'):
                    image=store.certificate(path.rsplit('/',1)[1])
                    if image is None: return self.respond(404,dict(error='资格证图片不存在'))
                    return self.respond(200,image[2],image[0])
                if path.startswith('/api/history/'):
                    return self.respond(200,dict(state=store.revision(int(path.rsplit('/',1)[1]))))
                if path=='/api/export':
                    if parse_qs(urlsplit(self.path).query).get('format')==['pdf']:
                        return self.pdf_report(store)
                    _,state=store.read(); buf=io.StringIO(); writer=csv.writer(buf)
                    writer.writerow(['姓名','单位','工号','容量筛查（模拟）','跨项目','实施期','职称计费','待补项','期间起','期间止','申报工日','常规容量','高负荷参考线','规则版本'])
                    def safe(v):
                        s=str(v)
                        return "'"+s if s.lstrip().startswith(('=','+','-','@')) or s.startswith(('\t','\r','\n')) else s
                    for r in analyze(state):
                        p=r['person']; w=r['worst'] or {}
                        writer.writerow([safe(v) for v in [p['name'],p.get('company',''),p['code'],w.get('label','无法判断'),*r['checks'].values(),r['pending_count'],w.get('start',''),w.get('end',''),w.get('demand',''),w.get('c0',''),w.get('c2',''),VERSION]])
                    return self.respond(200,buf.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8','expert-hours-review.csv')
                if path.startswith('/api/'): return self.respond(404,dict(error='不存在的接口'))
                dist=(ROOT/'dist').resolve()
                target=(dist/('index.html' if path=='/' else path.lstrip('/'))).resolve()
                if not target.is_relative_to(dist) or not target.is_file(): return self.respond(404,dict(error='页面不存在，请先运行 npm run build'))
                return self.respond(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            except (ValueError,KeyError,TypeError) as exc: self.respond(400,dict(error=str(exc)))
            except Exception:
                traceback.print_exc(); self.respond(500,dict(error='服务读取失败，请查看运行日志'))
        def do_POST(self):
            try:
                origin=self.headers.get('Origin')
                if origin and origin!='http://'+self.headers.get('Host',''): return self.respond(403,dict(error='拒绝跨站写入'))
                if not self.headers.get('Content-Type','').startswith('application/json'): return self.respond(415,dict(error='仅接受JSON请求'))
                store,path=self.route()
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>(100_000_000 if path in ('/api/save','/api/restore') else 20_000_000): return self.respond(413,dict(error='请求大小超出限制'))
                def reject_constant(x): raise ValueError('不接受非有限数字')
                payload=json.loads(self.rfile.read(size),parse_constant=reject_constant)
                if path=='/api/calendar-preview':
                    return self.respond(200,calendar_package(payload))
                if path=='/api/calendar-sync':
                    _,state=store.read()
                    url=payload.get('url', state.get('calendar_update', {}).get('url', ''))
                    return self.respond(200,fetch_intranet_calendar(url))
                if path=='/api/import-preview':
                    _,state=store.read()
                    return self.respond(200,import_preview(state,payload.get('file',''),payload.get('defaults')))
                if path=='/api/import-repair':
                    _,state=store.read()
                    return self.respond(200,repair_import_row(state,payload))
                if path=='/api/import-problems-export':
                    _,state=store.read()
                    template=ROOT/'public'/'project-hours-template.xlsx'
                    return self.respond(200,export_import_problems(template.read_bytes(),state,payload),
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pending-hours.xlsx')
                if path=='/api/template-refresh':
                    _,state=store.read()
                    return self.respond(200,refresh_template(payload.get('file',''),state),
                                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                        'project-hours-template-refreshed.xlsx')
                if path=='/api/delete-record':
                    return self.respond(200,dict(revision=store.delete_record(payload['kind'],payload['id'],payload['revision'],payload['actor'])))
                if path=='/api/restore-record':
                    return self.respond(200,dict(revision=store.restore_record(payload['id'],payload['revision'],payload['actor'])))
                if path not in ('/api/save','/api/restore'): return self.respond(404,dict(error='不存在的接口'))
                rev=store.save(payload['state'],payload['revision'],payload['actor'],payload.get('action','恢复备份'),restore=path=='/api/restore',certificates=payload.get('certificates'))
                self.respond(200,dict(revision=rev))
            except Conflict as exc: self.respond(409,dict(error=str(exc)))
            except (ValueError,KeyError,TypeError) as exc: self.respond(400,dict(error=str(exc)))
            except Exception:
                traceback.print_exc(); self.respond(500,dict(error='保存失败，未返回成功；请刷新核对台账版本'))
    return Handler

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8791)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data')
    args=parser.parse_args()
    stores={False:Store(args.data_dir/'ledger.sqlite3'),True:Store(args.data_dir/'demo.sqlite3',True)}
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_factory(stores))
    stop = threading.Event()
    worker = threading.Thread(target=calendar_sync_loop, args=(stores, Conflict, stop), daemon=True)
    worker.start()
    print(f'专家工时核验 v{APP_VERSION}（模拟规则 v{VERSION}） http://127.0.0.1:{args.port}/',flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=12)

if __name__=='__main__': main()
