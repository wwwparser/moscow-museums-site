"""Resumeable crawl and verified extraction of admission tariffs/free-entry rules."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.admission_collector import crawl
from src.services.admission_extract import extract
ROOT=Path(__file__).resolve().parents[1]

def load(path):
    return {r['key']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())} if path.exists() else {}

def profiles():
    source=json.loads((ROOT/'data/event-profiles.json').read_text(encoding='utf8'))
    museums=json.loads((ROOT/'data/museums.json').read_text(encoding='utf8'))
    result={}
    from urllib.parse import urlparse
    for m in museums:
        for u in m['sites']:
            domain=urlparse(u).hostname.removeprefix('www.')
            if domain not in result:result[domain]={'domain':domain,'name':m['name'],'seeds':[u]}
    overrides=ROOT/'data/admission-profiles.json'
    if overrides.exists():
        for domain,row in json.loads(overrides.read_text(encoding='utf8')).items():
            if domain in result:result[domain].update(row)
    return sorted(result.values(),key=lambda p:(source[p['domain']]['adapter']=='generic',p['domain']))

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['crawl','extract','all'],default='all')
    ap.add_argument('--workers',type=int,default=6);ap.add_argument('--domains');ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--refresh',action='store_true');ap.add_argument('--provider',default='deepseek',choices=['deepseek','dahl','ikhdev'])
    args=ap.parse_args(argv)
    if not 1<=args.workers<=8:ap.error('workers must be between 1 and 8')
    if args.provider=='ikhdev' and args.stage!='crawl':ap.error('Free provider requires a serial rate-limited runner')
    docs_path=ROOT/'data/admission-documents.jsonl';result_path=ROOT/'data/admission-results.jsonl'
    docs=load(docs_path);results=load(result_path)
    selected=[p for p in profiles() if not args.domains or p['domain'] in args.domains.split(',')]
    selected=selected[:args.limit or None]
    if args.stage in ('crawl','all'):
        cache_dir=ROOT/'data/cache/admission';cache_dir.mkdir(parents=True,exist_ok=True)
        pending=[p for p in selected if args.refresh or p['domain'] not in docs]
        print('Scanning admission pages:',len(pending),flush=True)
        with docs_path.open('a',encoding='utf8') as f,ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i,future in enumerate(as_completed([pool.submit(crawl,p,cache_dir) for p in pending]),1):
                row=future.result();docs[row['key']]=row
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                print(f"[{i}/{len(pending)}] {row['key']} {row['status']} {len(row['documents'])} documents",flush=True)
    if args.stage in ('extract','all'):
        pending=[docs[p['domain']] for p in selected if p['domain'] in docs and (args.refresh or p['domain'] not in results or results[p['domain']].get('status')=='extraction_error')]
        def job(row):
            out={k:row[k] for k in ('key','name','checked_at','pages','errors','status','links')}
            out.update(tickets=[],free_rules=[],rejected=[],input_truncated=False)
            if row['documents']:
                try:
                    out.update(extract(row,args.provider,results.get(row['key'])));out['status']='facts_found' if out['tickets'] or out['free_rules'] else 'no_admission_facts'
                    if out['status']=='facts_found' and (out['rejected'] or out['input_truncated'] or out['errors']):out['status']='partial'
                except Exception as exc:out['status']='extraction_error';out['extraction_error']=str(exc)
            previous=results.get(row['key'])
            if (out['status']=='extraction_error' or (row['errors'] and not out['tickets'] and not out['free_rules'])) and previous and (previous.get('tickets') or previous.get('free_rules')):
                out['tickets']=previous['tickets'];out['free_rules']=previous['free_rules'];out['stale']=True
            return out
        print('Extracting admission facts:',len(pending),flush=True)
        with result_path.open('a',encoding='utf8') as f,ThreadPoolExecutor(max_workers=min(4,args.workers)) as pool:
            futures=[pool.submit(job,row) for row in pending]
            for i,future in enumerate(as_completed(futures),1):
                row=future.result();results[row['key']]=row
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                print(f"[{i}/{len(pending)}] {row['key']} {row['status']} tariffs {len(row['tickets'])} free rules {len(row['free_rules'])}",flush=True)
                if row.get('extraction_error','').endswith('HTTP 402'):
                    for other in futures:other.cancel()
                    raise RuntimeError('Provider balance exhausted; results saved')
    print('Admission sources cached:',len(docs),'extracted:',len(results),flush=True)

if __name__=='__main__':main()
