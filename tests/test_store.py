import sys,tempfile,unittest,json
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from store import Store,now,iso
class StoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'test.sqlite');self.a=self.s.save_account({'platform':'douyin','id':'own-id','name':'测试','verified':True});self.key=self.a['key']
 def tearDown(self):self.tmp.cleanup()
 def payload(self,views=100,collected=None):
  return {'collectedAt':collected or iso(),'source':'official_export','contents':[{'platform':'douyin','accountId':'own-id','id':'c1','title':'标题','type':'video','publishedAt':iso(now()-timedelta(days=2)),'views':views,'likes':10,'comments':None,'saves':0,'shares':1,'na':[],'viewMetric':'play_count','url':'https://www.douyin.com/video/123?token=secret'}]}
 def test_idempotent_and_latest_valid_snapshot(self):
  p=self.payload();self.s.ingest(self.key,p);self.s.ingest(self.key,p);d=self.s.dataset();self.assertEqual(len(d['contents']),1);self.assertEqual(d['contents'][0]['views'],100);self.assertIsNone(d['contents'][0]['comments']);self.assertEqual(d['contents'][0]['url'],'https://www.douyin.com/video/123')
 def test_bad_batch_is_atomic_and_preserves_prior(self):
  self.s.ingest(self.key,self.payload());p=self.payload(500);p['contents'].append({**p['contents'][0],'id':'bad','likes':-4})
  with self.assertRaises(ValueError):self.s.ingest(self.key,p)
  self.assertEqual(self.s.dataset()['contents'][0]['views'],100)
 def test_mixed_accounts_rejected(self):
  p=self.payload();p['contents'][0]['accountId']='someone-else'
  with self.assertRaises(ValueError):self.s.ingest(self.key,p)
  self.assertEqual(self.s.dataset()['contents'],[])
 def test_old_snapshot_never_overwrites_latest(self):
  self.s.ingest(self.key,self.payload(200));self.s.ingest(self.key,self.payload(100,iso(now()-timedelta(hours=1))));self.assertEqual(self.s.dataset()['contents'][0]['views'],200)
 def test_exposure_cannot_masquerade_as_views(self):
  p=self.payload();p['contents'][0]['viewMetric']='impressions'
  with self.assertRaises(ValueError):self.s.ingest(self.key,p)
 def test_unknown_coverage_remains_partial(self):
  p=self.payload();p['coverage']={'complete':True};self.s.ingest(self.key,p);self.assertFalse(self.s.accounts()[0]['coverageComplete'])
 def test_verified_pagination_coverage(self):
  p=self.payload();p['coverage']={'complete':True,'scope':'all_since_join','expectedCount':1,'evidence':'explicit verified export range'};self.s.ingest(self.key,p);self.assertTrue(self.s.accounts()[0]['coverageComplete'])
 def test_public_coverage_never_full(self):
  p=self.payload();p['source']='public_visible_page';p['coverage']={'complete':True,'scope':'all_since_join','expectedCount':1,'evidence':'page'};self.s.ingest(self.key,p);self.assertFalse(self.s.accounts()[0]['coverageComplete'])
 def test_job_claim_once_and_isolation(self):
  self.assertEqual(self.s.enqueue(self.key),1);self.assertEqual(self.s.enqueue(self.key),0);self.assertIsNone(self.s.claim(['douyin:other']));job=self.s.claim([self.key]);self.assertIsNotNone(job);self.assertIsNone(self.s.claim([self.key]));p=self.payload();self.s.ingest(self.key,p,job);self.assertEqual(self.s.dataset()['logs'][0]['status'],'success')
 def test_lease_required(self):
  self.s.enqueue(self.key);job=self.s.claim([self.key]);job['lease']='wrong'
  with self.assertRaises(ValueError):self.s.ingest(self.key,self.payload(),job)
 def test_failure_preserves_metrics_and_pauses_restrictions(self):
  self.s.ingest(self.key,self.payload());self.s.enqueue(self.key);job=self.s.claim([self.key]);self.s.fail_job({**job,'reason':'access_restricted'});self.assertEqual(self.s.accounts()[0]['state'],'paused');self.assertEqual(len(self.s.dataset()['contents']),1)
 def test_annotation_preserved_by_next_ingest(self):
  self.s.ingest(self.key,self.payload());self.s.annotate({'platform':'douyin','accountId':'own-id','id':'c1','topic':'品牌活动'});self.s.ingest(self.key,self.payload());self.assertEqual(self.s.dataset()['contents'][0]['topic'],'品牌活动')
 def test_future_collection_rejected(self):
  with self.assertRaises(ValueError):self.s.ingest(self.key,self.payload(collected=iso(now()+timedelta(hours=1))))
 def test_non_numeric_is_not_zero(self):
  p=self.payload();p['contents'][0]['views']='1万'
  with self.assertRaises(ValueError):self.s.ingest(self.key,p)
 def test_csv_prevalidates_all_accounts(self):
  raw='platform,accountId,id,title,publishedAt,type,views,viewMetric,collectedAt\n'
  raw+=f'douyin,own-id,c1,标题,{iso(now()-timedelta(days=2))},video,99,play_count,{iso()}\n'
  raw+=f'douyin,unknown,c1,标题,{iso(now()-timedelta(days=2))},video,99,play_count,{iso()}\n'
  with self.assertRaises(ValueError):self.s.import_file({'filename':'a.csv','text':raw})
  self.assertEqual(self.s.dataset()['contents'],[])
 def test_views_cannot_be_marked_not_applicable(self):
  p=self.payload();p['contents'][0]['na']=['views'];p['contents'][0]['views']=None
  with self.assertRaises(ValueError):self.s.ingest(self.key,p)
 def test_mixed_timezones_order_by_instant(self):
  p=self.payload(100);p['collectedAt']=(now()-timedelta(minutes=30)).astimezone(__import__('datetime').timezone(timedelta(hours=8))).isoformat()
  self.s.ingest(self.key,p);self.s.ingest(self.key,self.payload(200));self.assertEqual(self.s.dataset()['contents'][0]['views'],200)
 def test_delete_cascades(self):
  self.s.ingest(self.key,self.payload());self.s.remove(self.key);self.assertEqual(self.s.dataset()['contents'],[])
if __name__=='__main__':unittest.main()
