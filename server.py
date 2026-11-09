"""Local application server, atomic shared SQLite state and append-only revisions."""
import argparse, csv, io, json, mimetypes, sqlite3, traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
from engine import VERSION, empty_state, validate, analyze
from sample_data import demo_state

ROOT=Path(__file__).resolve().parent
APP_VERSION=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']

def stamp(): return datetime.now(timezone.utc).isoformat()
def dumps(value): return json.dumps(value,ensure_ascii=False,allow_nan=False)

class Conflict(Exception): pass

class Store:
    def __init__(self,path,demo=False):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS current (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY, at TEXT, actor TEXT, action TEXT, body TEXT)')
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
    def save(self,state,revision,actor,action,restore=False):
        validate(state)
        if not isinstance(actor,str) or not actor.strip(): raise ValueError('填写本次操作人')
        if not isinstance(action,str) or not action.strip(): raise ValueError('缺少操作说明')
        body=dumps(state)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old_rev,old_body=db.execute('SELECT revision,body FROM current').fetchone()
            if old_rev!=revision: raise Conflict('台账已被其他页面修改，请刷新后重新编辑；当前输入仍保留')
            if restore:
                target=self.path.parent/'backups'; target.mkdir(exist_ok=True)
                name=f'{self.path.stem}-before-restore-r{old_rev}-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.json'
                (target/name).write_text(dumps(dict(schema_version=1,revision=old_rev,state=json.loads(old_body))),encoding='utf-8')
            rev=old_rev+1
            db.execute('UPDATE current SET revision=?,body=? WHERE id=1',(rev,body))
            db.execute('INSERT INTO history VALUES (?,?,?,?,?)',(rev,stamp(),actor.strip(),action.strip(),body))
        return rev
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
        def do_GET(self):
            try:
                store,path=self.route()
                if path=='/api/health': return self.respond(200,dict(app='expert-hours-review',version=VERSION,app_version=APP_VERSION,rule_version=VERSION))
                if path=='/api/state':
                    rev,state=store.read()
                    return self.respond(200,dict(revision=rev,state=state,results=analyze(state),history=store.history()))
                if path=='/api/backup':
                    rev,state=store.read()
                    return self.respond(200,dict(schema_version=1,revision=rev,exported_at=stamp(),state=state,history=store.history()),filename='expert-hours-backup.json')
                if path.startswith('/api/history/'):
                    return self.respond(200,dict(state=store.revision(int(path.rsplit('/',1)[1]))))
                if path=='/api/export':
                    _,state=store.read(); buf=io.StringIO(); writer=csv.writer(buf)
                    writer.writerow(['姓名','单位','工号','容量筛查（模拟）','跨项目','实施期','职称计费','待补项','期间起','期间止','申报工日','常规容量','高负荷参考线','规则版本'])
                    def safe(v):
                        s=str(v)
                        return "'"+s if s.lstrip().startswith(('=','+','-','@')) or s.startswith(('\t','\r','\n')) else s
                    for r in analyze(state):
                        p=r['person']; w=r['worst'] or {}
                        writer.writerow([safe(v) for v in [p['name'],p['company'],p['code'],w.get('label','无法判断'),*r['checks'].values(),r['pending_count'],w.get('start',''),w.get('end',''),w.get('demand',''),w.get('c0',''),w.get('c2',''),VERSION]])
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
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>20_000_000: return self.respond(413,dict(error='请求大小超出限制'))
                def reject_constant(x): raise ValueError('不接受非有限数字')
                payload=json.loads(self.rfile.read(size),parse_constant=reject_constant)
                store,path=self.route()
                if path not in ('/api/save','/api/restore'): return self.respond(404,dict(error='不存在的接口'))
                rev=store.save(payload['state'],payload['revision'],payload['actor'],payload.get('action','恢复备份'),restore=path=='/api/restore')
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
    print(f'专家工时核验 v{VERSION}: http://127.0.0.1:{args.port}/',flush=True)
    server.serve_forever()

if __name__=='__main__': main()
