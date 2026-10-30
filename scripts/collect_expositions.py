"""Crawl official collection/about pages and prepare evidence batches for internal Luna."""
import argparse,json,sys,time,zlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.http_client import fetch
from src.services.exposition import domain,extract_page,fingerprint
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/exposition'

def load(path):
    return {r['key']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())} if path.exists() else {}

def crawl(key,museums,required_sources=()):
    row={'key':key,'checked_at':datetime.now(timezone.utc).isoformat(),'museums':museums,'documents':[],'errors':[]}
    seeds=list(dict.fromkeys(u for m in museums for u in m['sites'] if domain(u)==key))
    pending=list(dict.fromkeys(seeds[:1]+list(required_sources)));seen=set();candidates=[]
    for _ in range(max(4,len(pending)+1)):
        if not pending:
            pending=[u for u in candidates if u not in seen][:1]
        if not pending:break
        url=pending.pop(0)
        if url in seen:continue
        seen.add(url)
        try:
            html,final=fetch(url,max_bytes=2_000_000)
            if domain(final)!=key:
                row['errors'].append({'url':url,'error':'Different-domain redirect: '+final});continue
            doc=extract_page(html,final,limit=8500)
            if len(doc['text'])>=120:row['documents'].append({k:doc[k] for k in ('source','title','text')})
            candidates.extend(doc['links'])
            if len(seen)==1:
                # Prefer curated collection pages over duplicate home-page URLs.
                candidates.extend(seeds[1:3])
        except Exception as exc:row['errors'].append({'url':url,'error':str(exc)[:300]})
        time.sleep(.25)
    row['evidence_hash']=fingerprint(row['documents'])
    row['status']='ready' if row['documents'] else 'unavailable'
    return row

def prepare(rows):
    items=[r for r in rows.values() if r['documents']]
    items.sort(key=lambda r:r['key'])
    OUT.mkdir(parents=True,exist_ok=True)
    # One evidence file per source keeps agent reads bounded and resumable.
    for row in items:(OUT/(row['key']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    notes_path=ROOT/'data/exposition-notes.json'
    reviewed=json.loads(notes_path.read_text(encoding='utf8')).get('reviews',{}) if notes_path.exists() else {}
    pending=[r for r in items if reviewed.get(r['key'],{}).get('evidence_hash')!=r['evidence_hash']]
    for part in range(3):
        batch=[r for r in pending if zlib.crc32(r['key'].encode())%3==part]
        (OUT/f'batch-{part+1}.json').write_text(json.dumps([{'key':r['key'],'file':str(OUT/(r['key']+'.json')),'museums':r['museums']} for r in batch],ensure_ascii=False,indent=2),encoding='utf8')
    summary={'checked_sources':len(rows),'readable_sources':len(items),'unavailable_sources':sum(not r['documents'] for r in rows.values()),'pending_luna':len(pending),'processor':'internal-luna','prepared_at':datetime.now(timezone.utc).isoformat()}
    (ROOT/'data/exposition-queue.json').write_text(json.dumps({'processor':'internal-luna','pending_luna':len(pending),'items':[{'key':r['key'],'file':str(OUT/(r['key']+'.json')),'evidence_hash':r['evidence_hash']} for r in pending]},ensure_ascii=False,indent=2),encoding='utf8')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=10);ap.add_argument('--limit',type=int,default=0);ap.add_argument('--refresh',action='store_true');ap.add_argument('--prepare-only',action='store_true');args=ap.parse_args()
    path=ROOT/'data/exposition-documents.jsonl';rows=load(path)
    if args.prepare_only:prepare(rows);return
    museums=json.loads((ROOT/'data/museums.json').read_text(encoding='utf8'));groups={}
    for m in museums:
        for key in dict.fromkeys(domain(u) for u in m['sites']):
            if key:groups.setdefault(key,[]).append({k:m[k] for k in ('id','name','address','sites')})
    jobs=[(k,v) for k,v in groups.items() if args.refresh or k not in rows][:args.limit or None]
    notes_path=ROOT/'data/exposition-notes.json'
    approved=json.loads(notes_path.read_text(encoding='utf8')).get('museums',{}) if notes_path.exists() else {}
    required={}
    for note in approved.values():
        for fact in note['facts']:
            if domain(fact['source'])==note['domain']:required.setdefault(note['domain'],set()).add(fact['source'])
    with path.open('a',encoding='utf8') as output,ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(crawl,k,ms,sorted(required.get(k,[]))) for k,ms in jobs]
        for i,future in enumerate(as_completed(futures),1):
            row=future.result();old=rows.get(row['key'])
            if not row['documents'] and old and old['documents']:
                row['documents']=old['documents'];row['evidence_hash']=old['evidence_hash'];row['stale']=True;row['last_success_at']=old.get('last_success_at',old['checked_at'])
            else:row['last_success_at']=row['checked_at'] if row['documents'] else ''
            rows[row['key']]=row;output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
            # Available immediately for research while the rest of the crawl runs.
            OUT.mkdir(parents=True,exist_ok=True)
            (OUT/(row['key']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
            print(f"expositions {i}/{len(jobs)}: {row['key']} ({len(row['documents'])} pages)",flush=True)
    prepare(rows)
if __name__=='__main__':main()
