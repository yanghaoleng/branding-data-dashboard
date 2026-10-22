#!/usr/bin/env python3
import json,os,secrets,threading,time,traceback
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from store import Store
ROOT=Path(__file__).resolve().parent
store=Store(os.environ.get('BRANDING_DB',str(ROOT.parent/'.local/branding.sqlite')))
ADMIN=os.environ.get('BRANDING_ADMIN_TOKEN','')
COLLECTOR=os.environ.get('BRANDING_COLLECTOR_TOKEN','')
if len(ADMIN)<24 or len(COLLECTOR)<24:raise SystemExit('Set distinct BRANDING_ADMIN_TOKEN and BRANDING_COLLECTOR_TOKEN (24+ chars).')
if ADMIN==COLLECTOR:raise SystemExit('Admin and collector credentials must differ.')
rate={};rate_lock=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    server_version='BrandingAPI/1'
    def log_message(self,*args):pass
    def send_json(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def authorized(self,collector=False):
        auth=self.headers.get('Authorization','');expected=COLLECTOR if collector else ADMIN
        return auth.startswith('Bearer ') and secrets.compare_digest(auth[7:],expected)
    def auth_gate(self,collector=False):
        if self.authorized(collector):return True
        ip=self.client_address[0]
        with rate_lock:
            ts=time.time();recent=[t for t in rate.get(ip,[]) if ts-t<60];recent.append(ts);rate[ip]=recent
            if len(rate)>1000:rate.clear()
        self.send_json({'error':'访问密钥无效或未提供'},429 if len(recent)>15 else 401);return False
    def route(self):return urlsplit(self.path).path.removeprefix('/brandingdatabse/api')
    def do_GET(self):
        path=self.route()
        if path=='/health':return self.send_json({'ok':True,'version':'1.0.0','scope':'owned-media'})
        if path=='/public/config':return self.send_json({'candidates':json.loads((ROOT/'candidates.json').read_text())})
        if not self.auth_gate():return
        if path=='/dataset':return self.send_json(store.dataset())
        self.send_json({'error':'接口不存在'},404)
    def do_POST(self):
        path=self.route();collector=path.startswith('/worker/')
        if not self.auth_gate(collector):return
        origin=self.headers.get('Origin')
        if origin and origin not in ('https://mikeywa.site','https://www.mikeywa.site','http://127.0.0.1:5178','http://localhost:5178'):return self.send_json({'error':'请求来源不符'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<2 or length>8*1024*1024:return self.send_json({'error':'请求体应在2字节至8MB之间'},413)
            p=json.loads(self.rfile.read(length))
            if not isinstance(p,dict):raise ValueError('请求需为对象')
            if path=='/accounts':return self.send_json({'account':store.save_account(p),'message':'已保存账号配置'})
            if path=='/accounts/update':return self.send_json({'account':store.save_account(p,True),'message':'账号已更新'})
            if path=='/accounts/remove':store.remove(p.get('key'));return self.send_json({'message':'账号已移除'})
            if path=='/sync':
                n=store.enqueue(p.get('accountKey','all'));return self.send_json({'message':f'已创建 {n} 个同步任务，等待在线采集器。后台导出账号请使用导入。'})
            if path=='/import':
                count=store.import_file(p);return self.send_json({'message':f'已校验并导入 {count} 条指标记录'})
            if path=='/contents/annotate':store.annotate(p);return self.send_json({'message':'议题已保存'})
            if path=='/worker/claim':return self.send_json({'job':store.claim(p.get('accountKeys'))})
            if path=='/worker/result':
                n=store.ingest(p.get('accountKey'),p,p);return self.send_json({'written':n})
            if path=='/worker/fail':store.fail_job(p);return self.send_json({'ok':True})
            self.send_json({'error':'接口不存在'},404)
        except (ValueError,KeyError,TypeError,OverflowError) as e:self.send_json({'error':str(e)[:250]},400)
        except Exception:self.send_json({'error':'存储暂时不可用，请稍后重试'},500)

def scheduler():
    while True:
        try:store.schedule()
        except Exception:print('scheduler: storage unavailable',flush=True)
        time.sleep(45)
if __name__=='__main__':
    threading.Thread(target=scheduler,daemon=True).start()
    port=int(os.environ.get('BRANDING_PORT','8836'))
    print(f'Branding API listening on loopback:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
