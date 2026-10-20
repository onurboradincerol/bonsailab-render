import copy,hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import app as server

ROOT=Path(__file__).resolve().parent
def sample():
    return {'species_id':'T04','season':'year_round','climate':'mild','phase':'pre','pot':'air','location':'outdoor','light':'filtered','wind':'low','watering':'daily','height':8,'volume':2000,'inventory':[{'name':n,'available':True,'grain_group':'medium'} for n in ('Pomza','Lav taşı','Torf','Kokopit','Perlit')]}

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client=server.app.test_client()
        with server.CACHE_LOCK:server.CACHE.clear()

    def test_config_and_health_match_engine_identity(self):
        self.assertEqual(self.client.get('/api/config').json,server.DB)
        health=self.client.get('/healthz');self.assertEqual(health.status_code,200)
        self.assertEqual(health.json['database_sha256'],server.DB_HASH)
        self.assertEqual(health.json['execution'],'server')

    def test_page_uses_http_and_has_no_browser_python_runtime(self):
        html=self.client.get('/').text;js=self.client.get('/static/app.js').text
        self.assertIn('Karışım değerleri tahminidir',html)
        self.assertNotIn('engine-client.js',html);self.assertNotIn('BonsaiEngine',js)
        self.assertIn("fetch('/api/calculate'",js)
        self.assertEqual(self.client.get('/engine/core.py').status_code,404)
        self.assertEqual(self.client.get('/runtime/pyodide.asm.wasm').status_code,404)

    def test_replays_40_species_and_80_variants_without_formula_changes(self):
        cases=json.loads((ROOT/'tests/cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cases),40)
        for case in cases:
            response=self.client.post('/api/calculate',json=case['request'])
            self.assertEqual(response.status_code,200)
            for key,value in case['expected_sha256'].items():
                actual=hashlib.sha256(json.dumps(response.json[key],ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
                self.assertEqual(actual,value)

    def test_same_input_is_cached_without_changing_output(self):
        first=self.client.post('/api/calculate',json=sample());second=self.client.post('/api/calculate',json=sample())
        self.assertEqual(first.headers['X-Bonsai-Cache'],'MISS');self.assertEqual(second.headers['X-Bonsai-Cache'],'HIT')
        self.assertEqual(first.data,second.data)

    def test_changed_input_cannot_reuse_old_cache(self):
        p=sample();first=self.client.post('/api/calculate',json=p);p['height']=12
        second=self.client.post('/api/calculate',json=p)
        self.assertNotEqual(first.json['request_sha256'],second.json['request_sha256'])
        self.assertEqual(second.headers['X-Bonsai-Cache'],'MISS')

    def test_busy_worker_returns_retry_and_health_stays_available(self):
        self.assertTrue(server.CALCULATION.acquire(blocking=False))
        try:
            response=self.client.post('/api/calculate',json=sample())
            self.assertEqual(response.status_code,429);self.assertEqual(response.headers['Retry-After'],'2')
            self.assertEqual(self.client.get('/healthz').status_code,200)
        finally:server.CALCULATION.release()

    def test_cached_result_is_available_while_other_calculation_busy(self):
        first=self.client.post('/api/calculate',json=sample());server.CALCULATION.acquire()
        try:
            response=self.client.post('/api/calculate',json=sample())
            self.assertEqual(response.status_code,200);self.assertEqual(response.data,first.data)
        finally:server.CALCULATION.release()

    def test_cache_has_ttl_and_capacity_bounds(self):
        self.client.post('/api/calculate',json=sample())
        with server.CACHE_LOCK:
            key=next(iter(server.CACHE));created,blob=server.CACHE[key]
            server.CACHE[key]=(created-server.CACHE_TTL-1,blob)
        self.assertIsNone(server.cache_get(key))
        with patch.object(server,'CACHE_MAX',2):
            for height in (4,8,12):self.client.post('/api/calculate',json={**sample(),'height':height})
            self.assertEqual(len(server.CACHE),2)

    def test_cross_site_json_is_rejected_and_same_origin_allowed(self):
        self.assertEqual(self.client.post('/api/calculate',json=sample(),headers={'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/calculate',json=sample(),headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.client.post('/api/calculate',json=sample(),headers={'Origin':'http://localhost'}).status_code,200)

    def test_json_content_type_and_malformed_data(self):
        self.assertEqual(self.client.post('/api/calculate',data='{}',content_type='text/plain').status_code,415)
        self.assertEqual(self.client.post('/api/calculate',data='{oops',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post('/api/calculate',json=[]).status_code,400)

    def test_oversize_body_has_json_error(self):
        r=self.client.post('/api/calculate',data=' '*150001,content_type='application/json')
        self.assertEqual(r.status_code,413);self.assertIn('error',r.json)

    def test_nonfinite_values_and_invalid_species_are_rejected(self):
        p=sample();p['height']=float('nan')
        self.assertEqual(self.client.post('/api/calculate',data=json.dumps(p),content_type='application/json').status_code,400)
        p=sample();p['species_id']='wrong'
        self.assertEqual(self.client.post('/api/calculate',json=p).status_code,400)

    def test_failure_releases_calculation_slot(self):
        p=sample();p['inventory']=[]
        self.assertEqual(self.client.post('/api/calculate',json=p).status_code,400)
        self.assertEqual(self.client.post('/api/calculate',json=sample()).status_code,200)

    def test_no_store_and_security_headers(self):
        for route in ('/','/api/config','/healthz'):
            response=self.client.get(route)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')

if __name__=='__main__':unittest.main(verbosity=2)
