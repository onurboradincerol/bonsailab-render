"""BonsaiLAB V27: same-origin WSGI service, with bounded CPU work and cache."""
from __future__ import annotations
import hashlib,json,logging,os,sys,threading,time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask,Response,request,send_from_directory
from werkzeug.exceptions import BadRequest,RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'engine'))
from core import DB,DB_HASH,InputError,calculate

app=Flask(__name__,static_folder='static')
app.config.update(MAX_CONTENT_LENGTH=150000,PROPAGATE_EXCEPTIONS=False)
if os.environ.get('RENDER')=='true':app.wsgi_app=ProxyFix(app.wsgi_app,x_for=0,x_proto=1,x_host=0,x_port=0,x_prefix=0)
if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):app.config['TRUSTED_HOSTS']=[os.environ['RENDER_EXTERNAL_HOSTNAME'],'localhost','127.0.0.1']
CALCULATION=threading.BoundedSemaphore(1)
CACHE_LOCK=threading.Lock();CACHE=OrderedDict();CACHE_TTL=900;CACHE_MAX=64

def json_response(data,status=200):
    return Response(json.dumps(data,ensure_ascii=False,allow_nan=False),status=status,content_type='application/json; charset=utf-8')

@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    response.headers['Cache-Control']='no-cache' if request.path.startswith('/static/') else 'no-store'
    return response

@app.get('/')
def index():return send_from_directory(ROOT,'index.html')

@app.get('/icon.svg')
def icon():return send_from_directory(ROOT,'icon.svg')

@app.get('/manifest.webmanifest')
def manifest():return send_from_directory(ROOT,'manifest.webmanifest')

@app.get('/healthz')
def health():return json_response({'status':'ok','application':'BonsaiLAB V27','execution':'server','database_sha256':DB_HASH})

@app.get('/api/config')
def config():return json_response(DB)

def cache_get(key):
    with CACHE_LOCK:
        item=CACHE.get(key)
        if not item:return None
        created,blob=item
        if time.monotonic()-created>CACHE_TTL:
            del CACHE[key];return None
        CACHE.move_to_end(key);return blob

@app.post('/api/calculate')
def calculation():
    if request.mimetype!='application/json':return json_response({'error':'Content-Type application/json olmalı.'},415)
    origin=request.headers.get('Origin')
    if origin:
        parsed=urlsplit(origin)
        if parsed.scheme not in ('http','https') or origin.rstrip('/')!=request.host_url.rstrip('/'):
            return json_response({'error':'Başka bir siteden gelen hesap isteği kabul edilmez.'},403)
    if request.headers.get('Sec-Fetch-Site')=='cross-site':return json_response({'error':'Başka bir siteden gelen hesap isteği kabul edilmez.'},403)
    try:
        payload=request.get_json()
        if not isinstance(payload,dict):raise InputError('İstek bir nesne olmalı.')
        key=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    except (BadRequest,ValueError,TypeError):return json_response({'error':'Geçerli bir JSON hesap isteği gönder.'},400)
    blob=cache_get(key)
    if blob is not None:
        response=Response(blob,content_type='application/json; charset=utf-8');response.headers['X-Bonsai-Cache']='HIT';return response
    if not CALCULATION.acquire(blocking=False):
        response=json_response({'error':'Sunucu önceki hesabı tamamlıyor; kısa süre sonra yeniden denenecek.'},429);response.headers['Retry-After']='2';return response
    try:
        blob=cache_get(key)
        hit=blob is not None
        if blob is None:
            result=calculate(payload)
            blob=json.dumps(result,ensure_ascii=False,allow_nan=False).encode()
            with CACHE_LOCK:
                CACHE[key]=(time.monotonic(),blob);CACHE.move_to_end(key)
                while len(CACHE)>CACHE_MAX:CACHE.popitem(last=False)
        response=Response(blob,content_type='application/json; charset=utf-8');response.headers['X-Bonsai-Cache']='HIT' if hit else 'MISS';return response
    except InputError as error:return json_response({'error':str(error)},400)
    except Exception:
        app.logger.exception('Calculation failed')
        return json_response({'error':'Sunucu hesabı tamamlayamadı. Biraz sonra tekrar dene.'},500)
    finally:CALCULATION.release()

@app.errorhandler(RequestEntityTooLarge)
def too_large(error):return json_response({'error':'Hesap isteği çok büyük.'},413)

@app.errorhandler(404)
def missing(error):return json_response({'error':'Adres bulunamadı.'},404)

@app.errorhandler(405)
def wrong_method(error):return json_response({'error':'Bu adreste yöntem desteklenmiyor.'},405)

if __name__=='__main__':app.run(host='127.0.0.1',port=int(os.environ.get('PORT','8907')),debug=False,threaded=True)
