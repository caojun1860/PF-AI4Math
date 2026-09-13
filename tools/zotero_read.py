"""Bounded read-only Zotero Desktop API access; requires Zotero local API enabled."""
import argparse,json,re,urllib.request,urllib.parse,urllib.error

BASE='http://127.0.0.1:23119/api/users/0'
def get(path,params=None):
 url=BASE+path
 if params:url+='?'+urllib.parse.urlencode(params)
 req=urllib.request.Request(url,headers={'Zotero-API-Version':'3','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=10) as response:
  return json.load(response)

def compact(item):
 d=item.get('data',item)
 return {k:d.get(k) for k in ['key','itemType','title','creators','date','DOI','url','parentItem','contentType'] if d.get(k) is not None}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('command',choices=['search','item','children'])
 p.add_argument('value',help='search text or eight-character Zotero item key')
 args=p.parse_args()
 if args.command!='search' and not re.fullmatch('[A-Z0-9]{8}',args.value):p.error('Item key must contain eight uppercase letters/digits')
 if args.command=='search':
  if not args.value.strip():p.error('Search text is required')
  result=[compact(x) for x in get('/items/top',{'q':args.value,'limit':10,'format':'json'})]
 elif args.command=='item':result=compact(get('/items/'+args.value))
 else:result=[compact(x) for x in get('/items/'+args.value+'/children',{'limit':10,'format':'json'})]
 print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
 try:main()
 except (urllib.error.URLError,TimeoutError) as e:
  raise SystemExit('Zotero read failed: '+str(e))
