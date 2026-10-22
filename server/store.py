"""Private brand metrics store. stdlib-only; no platform credentials are accepted."""
import csv, io, json, os, re, sqlite3, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
TZ=timezone(timedelta(hours=8))
FIELDS=('views','likes','comments','saves','shares')
PLATFORMS=('douyin','xiaohongshu','channels')
def now(): return datetime.now(timezone.utc)
def iso(dt=None): return (dt or now()).isoformat(timespec='seconds')
def parse_date(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None: raise ValueError()
        return dt.astimezone(timezone.utc)
    except (ValueError,TypeError): raise ValueError('日期必须包含时区，例如 2026-10-22T12:00:00+08:00')
def safe_url(value, platform=None):
    from urllib.parse import urlparse
    if not value:return ''
    u=urlparse(str(value))
    hosts={'douyin':('douyin.com',),'xiaohongshu':('xiaohongshu.com',),'channels':('weixin.qq.com',)}
    allowed=hosts.get(platform,('douyin.com','xiaohongshu.com','weixin.qq.com'))
    if u.scheme!='https' or u.username or not any(u.hostname==h or (u.hostname or '').endswith('.'+h) for h in allowed):raise ValueError('链接必须是对应平台的 HTTPS 地址')
    # Strip authentication-like tracking tokens: never persist session materials.
    return u._replace(query='',fragment='').geturl()
def text(value,maxlen=160):return str(value or '').strip()[:maxlen]
class Store:
    def __init__(self,path):
        self.path=str(path)
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS accounts(key TEXT PRIMARY KEY,platform TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS contents(account_key TEXT NOT NULL,id TEXT NOT NULL,published_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(account_key,id),FOREIGN KEY(account_key) REFERENCES accounts(key) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS content_metrics_daily(account_key TEXT NOT NULL,content_id TEXT NOT NULL,day TEXT NOT NULL,collected_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(account_key,content_id,day),FOREIGN KEY(account_key,content_id) REFERENCES contents(account_key,id) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS contents_dates ON contents(published_at,account_key);
            CREATE TABLE IF NOT EXISTS collection_logs(id TEXT PRIMARY KEY,account_key TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,available_at TEXT NOT NULL,lease TEXT,lease_until TEXT,message TEXT NOT NULL DEFAULT '',FOREIGN KEY(account_key) REFERENCES accounts(key) ON DELETE CASCADE);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON collection_logs(account_key) WHERE status IN ('queued','running');
            ''')
        try:os.chmod(self.path,0o600)
        except OSError:pass
    def connect(self):
        c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
    def accounts(self):
        with self.connect() as c:return [json.loads(r['payload']) for r in c.execute('SELECT payload FROM accounts ORDER BY key')]
    def account(self,key,c=None):
        if c is None:
            with self.connect() as c:return self.account(key,c)
        r=c.execute('SELECT payload FROM accounts WHERE key=?',(key,)).fetchone()
        if not r:raise ValueError('账号不存在')
        return json.loads(r['payload'])
    def save_account(self,p,update=False):
        with self.connect() as c:
            if update:
                a=self.account(p.get('key'),c)
                for k in ('name','profileUrl','mode','intervalHours','verified','state'):
                    if k in p:a[k]=p[k]
            else:
                platform=p.get('platform');aid=text(p.get('id'))
                if platform not in PLATFORMS or not re.fullmatch(r'[A-Za-z0-9_.@-]{2,160}',aid):raise ValueError('请选择平台并填写稳定平台账号 ID（至少2个字符）')
                a={'key':platform+':'+aid,'platform':platform,'id':aid,'name':text(p.get('name'),80),'mode':p.get('mode','public'),'profileUrl':p.get('profileUrl',''),'verified':p.get('verified',False),'intervalHours':p.get('intervalHours',24),'state':'pending','lastSync':None,'joinedAt':iso(),'coverageComplete':False,'nextDue':iso()}
                if c.execute('SELECT 1 FROM accounts WHERE key=?',(a['key'],)).fetchone():raise ValueError('此平台账号已存在')
            if not text(a.get('name'),80):raise ValueError('请填写账号显示名称')
            if a['mode'] not in ('public','authorized','export'):raise ValueError('不支持此接入方式')
            if a['intervalHours'] not in (6,12,24):raise ValueError('同步频率支持6、12或24小时')
            if a['state'] not in ('pending','ready','failed','paused'):raise ValueError('无效采集状态')
            if not isinstance(a['verified'],bool):raise ValueError('账号归属需明确确认')
            a['profileUrl']=safe_url(a.get('profileUrl'),a['platform']);a['name']=text(a['name'],80)
            c.execute('INSERT INTO accounts VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',(a['key'],a['platform'],a['id'],json.dumps(a,ensure_ascii=False)))
            return a
    def remove(self,key):
        with self.connect() as c:c.execute('DELETE FROM accounts WHERE key=?',(key,))
    def dataset(self):
        with self.connect() as c:
            accounts=[json.loads(r['payload']) for r in c.execute('SELECT payload FROM accounts ORDER BY key')]
            records=[]
            for r in c.execute('''SELECT c.payload AS content,m.payload AS metrics FROM contents c JOIN content_metrics_daily m ON c.account_key=m.account_key AND c.id=m.content_id WHERE m.collected_at=(SELECT MAX(m2.collected_at) FROM content_metrics_daily m2 WHERE m2.account_key=c.account_key AND m2.content_id=c.id)'''):
                records.append({**json.loads(r['content']),**json.loads(r['metrics'])})
            logs=[]
            names={a['key']:a['name'] for a in accounts}
            for r in c.execute('SELECT * FROM collection_logs ORDER BY created_at DESC LIMIT 100'):
                logs.append({'id':r['id'],'accountKey':r['account_key'],'accountName':names.get(r['account_key']),'status':r['status'],'createdAt':r['created_at'],'message':r['message']})
            return {'accounts':accounts,'contents':records,'logs':logs,'isDemo':False,'generatedAt':iso()}
    def enqueue(self,key='all'):
        count=0
        with self.connect() as c:
            accounts=[self.account(key,c)] if key!='all' else [json.loads(r[0]) for r in c.execute('SELECT payload FROM accounts')]
            for a in accounts:
                if a['state']=='paused' or a['mode']=='export':continue
                try:
                    c.execute('INSERT INTO collection_logs(id,account_key,status,created_at,updated_at,available_at,message) VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(12),a['key'],'queued',iso(),iso(),iso(),'等待本地采集器领取任务'))
                    count+=1
                except sqlite3.IntegrityError:pass
        return count
    def schedule(self):
        for a in self.accounts():
            if a['state']!='paused' and a['mode']!='export' and parse_date(a.get('nextDue') or a['joinedAt'])<=now():self.enqueue(a['key'])
        with self.connect() as c:
            for r in c.execute("SELECT * FROM collection_logs WHERE status='running' AND lease_until<?",(iso(),)).fetchall():
                status='queued' if r['attempt']<3 else 'failed'
                c.execute('UPDATE collection_logs SET status=?,lease=NULL,available_at=?,message=?,updated_at=? WHERE id=?',(status,iso(now()+timedelta(minutes=5)), '采集器未在任务时限内回传；请检查本机采集器',iso(),r['id']))
                if status=='failed':
                    a=self.account(r['account_key'],c);a.update(state='failed',nextDue=iso(now()+timedelta(hours=a['intervalHours'])))
                    c.execute('UPDATE accounts SET payload=? WHERE key=?',(json.dumps(a,ensure_ascii=False),a['key']))
    def claim(self,keys):
        if not isinstance(keys,list) or not keys or len(keys)>100:raise ValueError('需要本机已配置的账号列表')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            marks=','.join('?' for _ in keys)
            r=c.execute(f"SELECT * FROM collection_logs WHERE status='queued' AND available_at<=? AND account_key IN ({marks}) ORDER BY created_at LIMIT 1",[iso(),*keys]).fetchone()
            if not r:return None
            a=self.account(r['account_key'],c)
            if a['state']=='paused':return None
            lease=secrets.token_urlsafe(24)
            c.execute("UPDATE collection_logs SET status='running',lease=?,lease_until=?,attempt=attempt+1,updated_at=?,message=? WHERE id=?",(lease,iso(now()+timedelta(minutes=20)),iso(),'本地采集器正在读取',r['id']))
            return {'id':r['id'],'lease':lease,'account':a}
    def normalize(self,a,p):
        collected=parse_date(p.get('collectedAt'))
        if collected>now()+timedelta(minutes=5):raise ValueError('采集时间不能在未来')
        records=p.get('contents')
        if not isinstance(records,list) or len(records)>20000:raise ValueError('作品列表格式错误或超过20000条')
        source=p.get('source')
        if source not in ('official_export','creator_visible_page','public_visible_page'):raise ValueError('需要明确的数据来源')
        seen=set();out=[]
        for r in records:
            if r.get('accountId')!=a['id'] or r.get('platform')!=a['platform']:raise ValueError('账号归属不符，拒绝混入其他账号的数据')
            cid=text(r.get('id'))
            if not cid or cid in seen:raise ValueError('内容 ID 缺失或本批次重复')
            seen.add(cid);published=parse_date(r.get('publishedAt'))
            if published>now()+timedelta(minutes=5) or published>collected:raise ValueError('发布时间不能晚于采集时间')
            if r.get('type') not in ('video','image'):raise ValueError('内容类型必须为video或image')
            na=r.get('na',[])
            if not isinstance(na,list) or any(k not in FIELDS[1:] for k in na):raise ValueError('不适用字段格式错误')
            metrics={}
            for k in FIELDS:
                v=r.get(k)
                if v is not None and (type(v) is not int or v<0 or v>9007199254740991):raise ValueError('指标必须为非负整数或null，不接收估算数值')
                if k in na and v is not None:raise ValueError('不适用字段不能同时有数值')
                metrics[k]=v
            if metrics['views'] is not None and r.get('viewMetric') not in ('play_count','view_count','read_count'):raise ValueError('观看指标需声明原始口径；曝光量不能当播放量')
            if not text(r.get('title'),500):raise ValueError('作品标题不能为空')
            content={'id':cid,'platform':a['platform'],'accountId':a['id'],'title':text(r['title'],500),'publishedAt':iso(published),'type':r['type'],'url':safe_url(r.get('url'),a['platform'])}
            metrics.update(na=na,collectedAt=iso(collected),source={'official_export':'创作者后台导出（导入者声明）','creator_visible_page':'授权创作者后台可见页','public_visible_page':'平台公开可见页'}[source],viewMetric=r.get('viewMetric'),validity='partial' if any(metrics[k] is None and k not in na for k in FIELDS) else 'complete')
            out.append((content,metrics))
        cov=p.get('coverage') or {}
        complete=bool(cov.get('complete') is True and cov.get('scope')=='all_since_join' and type(cov.get('expectedCount')) is int and cov['expectedCount']==len(seen) and text(cov.get('evidence'),500) and source!='public_visible_page')
        return collected,out,complete
    def ingest(self,key,p,job=None):
        a=self.account(key);collected,records,complete=self.normalize(a,p)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if job:
                r=c.execute("SELECT * FROM collection_logs WHERE id=? AND status='running' AND lease=? AND account_key=? AND lease_until>?",(job['id'],job['lease'],key,iso())).fetchone()
                if not r:raise ValueError('任务租约无效或已过期')
            # Preserve metadata when an older import arrives after a newer snapshot.
            for content,metrics in records:
                latest=c.execute('SELECT MAX(collected_at) FROM content_metrics_daily WHERE account_key=? AND content_id=?',(key,content['id'])).fetchone()[0]
                if latest is None or iso(collected)>=latest:
                    old=c.execute('SELECT payload FROM contents WHERE account_key=? AND id=?',(key,content['id'])).fetchone()
                    if old:content['topic']=json.loads(old[0]).get('topic','')
                    c.execute('INSERT INTO contents VALUES(?,?,?,?) ON CONFLICT(account_key,id) DO UPDATE SET published_at=excluded.published_at,payload=excluded.payload',(key,content['id'],content['publishedAt'],json.dumps(content,ensure_ascii=False)))
                day=collected.astimezone(TZ).date().isoformat()
                c.execute('''INSERT INTO content_metrics_daily VALUES(?,?,?,?,?) ON CONFLICT(account_key,content_id,day) DO UPDATE SET collected_at=excluded.collected_at,payload=excluded.payload WHERE excluded.collected_at>=content_metrics_daily.collected_at''',(key,content['id'],day,iso(collected),json.dumps(metrics,ensure_ascii=False)))
            a=self.account(key,c)
            if not a['lastSync'] or iso(collected)>=a['lastSync']:
                a.update(lastSync=iso(collected),coverageComplete=complete,state='ready' if a['state']!='paused' else 'paused',nextDue=iso(now()+timedelta(hours=a['intervalHours'])))
                c.execute('UPDATE accounts SET payload=? WHERE key=?',(json.dumps(a,ensure_ascii=False),key))
            message=f'有效写入 {len(records)} 条作品；'+('覆盖已核验' if complete else '作品覆盖未完整核验')
            if job:c.execute("UPDATE collection_logs SET status='success',message=?,updated_at=?,lease=NULL WHERE id=?",(message,iso(),job['id']))
            else:c.execute('INSERT INTO collection_logs(id,account_key,status,created_at,updated_at,available_at,message) VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(12),key,'success',iso(),iso(),iso(),message))
        return len(records)
    def fail_job(self,p):
        # Enumerated reasons only. Never put browser response bodies or credentials in logs.
        messages={'login_required':'平台登录失效，请在本机重新登录','access_restricted':'平台访问受限，已停止自动重试','account_mismatch':'页面账号与配置不一致，拒绝写入','schema_changed':'平台页面结构变化，请更新采集适配配置','network':'网络连接失败，稍后有限重试','coverage_unknown':'未能核实作品列表，请检查采集范围'}
        reason=p.get('reason','schema_changed')
        with self.connect() as c:
            r=c.execute("SELECT * FROM collection_logs WHERE id=? AND status='running' AND lease=? AND lease_until>?",(p.get('id'),p.get('lease'),iso())).fetchone()
            if not r:raise ValueError('任务租约无效')
            retry=reason=='network' and r['attempt']<3
            c.execute('UPDATE collection_logs SET status=?,message=?,available_at=?,updated_at=?,lease=NULL WHERE id=?',('queued' if retry else 'failed',messages.get(reason,messages['schema_changed']),iso(now()+timedelta(minutes=5*r['attempt'])),iso(),r['id']))
            if not retry:
                a=self.account(r['account_key'],c);a.update(state='failed',nextDue=iso(now()+timedelta(hours=a['intervalHours'])))
                if reason in ('access_restricted','account_mismatch'):a['state']='paused'
                c.execute('UPDATE accounts SET payload=? WHERE key=?',(json.dumps(a,ensure_ascii=False),a['key']))
    def annotate(self,p):
        key=p.get('platform','')+':'+p.get('accountId','')
        with self.connect() as c:
            r=c.execute('SELECT payload FROM contents WHERE account_key=? AND id=?',(key,p.get('id'))).fetchone()
            if not r:raise ValueError('内容不存在')
            content=json.loads(r[0]);content['topic']=text(p.get('topic'),40)
            c.execute('UPDATE contents SET payload=? WHERE account_key=? AND id=?',(json.dumps(content,ensure_ascii=False),key,p['id']))
    def import_file(self,p):
        raw=p.get('text','');filename=p.get('filename','')
        if filename.endswith('.json'):
            data=json.loads(raw);return self.ingest(data['accountKey'],data)
        reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')),delimiter='\t' if filename.endswith('.tsv') else ',')
        groups={}
        for r in reader:
            key=r.get('platform','')+':'+r.get('accountId','');dt=r.get('collectedAt')
            group=groups.setdefault((key,dt),[])
            for k in FIELDS:
                value=r.get(k,'').strip()
                r[k]=None if value=='' else int(value)
            r['na']=[x for x in r.get('na','').split('|') if x]
            group.append(r)
        if not groups:raise ValueError('文件没有有效作品行')
        # Validate every batch before any write.
        for (key,dt),rows in groups.items():self.normalize(self.account(key),{'collectedAt':dt,'source':'official_export','contents':rows})
        count=0
        for (key,dt),rows in groups.items():count+=self.ingest(key,{'collectedAt':dt,'source':'official_export','contents':rows})
        return count
