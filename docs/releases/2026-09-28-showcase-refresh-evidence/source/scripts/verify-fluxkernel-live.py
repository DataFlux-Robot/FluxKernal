"""Verify ordinary + cache-busted payload bytes and trusted public TLS.
Usage: python verify-fluxkernel-live.py PAYLOAD EVIDENCE DEPLOYMENT_SHA
Requires httpx. Never disables TLS verification or uses local proxy settings.
"""
import concurrent.futures, hashlib, json, re, socket, ssl, sys, time
from pathlib import Path
import httpx
root,evidence,sha=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
evidence.mkdir(parents=True,exist_ok=True)
base='https://www.datafluxdynamics.ltd/'
probe=str(time.time_ns())
version=re.search(r'/fluxkernel/viewer\.js\?v=([a-f0-9]+)', (root/'technology/fluxkernel/index.html').read_text()).group(1)
paths=['technology/index.html','technology/fluxkernel/index.html']
paths += [p.relative_to(root).as_posix() for p in (root/'fluxkernel').rglob('*') if p.is_file()]
with httpx.Client(trust_env=False,timeout=120,follow_redirects=True) as client:
    def verify(path):
        expected=hashlib.sha256((root/path).read_bytes()).hexdigest()
        checks=[]
        published_query='?v='+version if path in ('fluxkernel/viewer.js','fluxkernel/phone.json','fluxkernel/car.json','fluxkernel/aircraft.json') else ''
        separator='&' if published_query else '?'
        for suffix in dict.fromkeys([published_query+separator+'release='+sha+'&probe='+probe,published_query,'']):
            response=client.get(base+path+suffix)
            assert response.status_code==200,(path,suffix,response.status_code)
            actual=hashlib.sha256(response.content).hexdigest()
            assert actual==expected,(path,suffix,'hash mismatch')
            checks.append({'query':suffix,'status':response.status_code,'sha256':actual,'bytes':len(response.content),'content_encoding':response.headers.get('content-encoding')})
        return {'path':path,'checks':checks}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(verify,paths))
    dns=client.get('https://cloudflare-dns.com/dns-query',params={'name':'www.datafluxdynamics.ltd','type':'A'},headers={'Accept':'application/dns-json'}).json()
ctx=ssl.create_default_context()
with socket.create_connection(('www.datafluxdynamics.ltd',443),timeout=30) as sock:
    with ctx.wrap_socket(sock,server_hostname='www.datafluxdynamics.ltd') as secure:
        cert=secure.getpeercert();tls={'version':secure.version(),'issuer':cert['issuer'],'subjectAltName':cert['subjectAltName'],'notAfter':cert['notAfter'],'trusted':True,'hostname_verified':ctx.check_hostname}
report={'deployment':sha,'base':base,'files':results,'dns':dns,'tls':tls}
(evidence/'live-integrity.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'verified_files':len(results),'published_urls_and_cachebusted_match':True,'tls':tls},ensure_ascii=False))
