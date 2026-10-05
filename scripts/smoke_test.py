"""Run inside the core container: python scripts/smoke_test.py."""
import json
import os
import time
import urllib.request

BASE=os.getenv('API_BASE','http://127.0.0.1:8000').rstrip('/')
def call(path,post=False):
    req=urllib.request.Request(BASE+path,method='POST' if post else 'GET')
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)

def main():
    print('Health:',call('/api/health'))
    r=call('/api/demo',True);jid=r['job']['id']
    print('Demo:',r['project']['id'])
    for _ in range(900):
        j=call('/api/jobs/'+jid)
        if j['status'] not in ('queued','running'):
            print(json.dumps(j,indent=2))
            if j['status']!='completed':raise SystemExit(1)
            print('PASS: montaggio reale completato. Apri la demo nell\'interfaccia.')
            break
        time.sleep(1)
    else:raise SystemExit('Test scaduto: controlla i log del container.')

if __name__ == "__main__":
    main()
