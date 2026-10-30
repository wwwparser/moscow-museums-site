"""Crawl admission sources and deterministically revalidate known evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.admission_collector import crawl
from src.services.admission_extract import validate
from src.services.admission_evidence import evidence_fingerprint
ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return {r['key']: r for r in map(json.loads, path.read_text(encoding='utf8').splitlines())} if path.exists() else {}


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


def validate_known(doc_row, previous):
    """Validate prior candidates only against the latest successfully crawled text."""
    out={k:doc_row.get(k) for k in ('key','name','checked_at','pages','errors','status','links')}
    out.update(tickets=[], free_rules=[], rejected=[], input_truncated=bool(previous.get('input_truncated')))
    for field in ('processor','luna_checked_at','evidence_hash','needs_luna_review','review_complete','review_exclusions'):
        if field in previous:out[field]=previous[field]
    if previous:
        candidates=previous.get('candidates') or {k: previous.get(k,[]) for k in ('tickets','free_rules')}
        documents=[]
        for d in doc_row.get('documents',[]):
            try: documents.append({'source':d['source'],'text':Path(d['file']).read_text(encoding='utf8')})
            except OSError: continue
        combined={}
        for d in documents: combined[d['source']]=combined.get(d['source'],'')+'\n'+d['text']
        if documents:
            current_hash=evidence_fingerprint(documents)
            out.update(validate(candidates,[{'source':u,'text':t} for u,t in combined.items()]))
            out['candidates']=candidates
            out['evidence_hash']=current_hash
            reviewed_at=previous.get('luna_checked_at') or (previous.get('checked_at','') if previous.get('processor')=='internal-luna' else '')
            previous_hash=previous.get('evidence_hash')
            if previous.get('processor')=='internal-luna' and previous_hash:
                review_needed=current_hash!=previous_hash
            else:
                review_needed=not reviewed_at or doc_row.get('checked_at','')>reviewed_at
            out['needs_luna_review']=bool(previous.get('needs_luna_review') or review_needed)
            out['status']='facts_found' if out['tickets'] or out['free_rules'] else 'no_admission_facts'
        elif previous.get('tickets') or previous.get('free_rules'):
            out['tickets']=previous['tickets'];out['free_rules']=previous['free_rules']
            out['rejected']=previous.get('rejected',[]);out['candidates']=candidates
            out['stale']=True;out['status']='stale'
    if doc_row.get('errors') and (out['tickets'] or out['free_rules']):
        out['status']='stale' if out.get('stale') else 'partial'
    if out.get('stale'):
        out['last_success_at']=previous.get('last_success_at') or previous.get('checked_at')
        out['last_attempt_at']=doc_row.get('checked_at')
    elif out['tickets'] or out['free_rules']:
        out['last_success_at']=doc_row.get('checked_at')
    return out


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['crawl','extract','all'],default='all')
    ap.add_argument('--workers',type=int,default=6);ap.add_argument('--domains');ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--refresh',action='store_true');ap.add_argument('--provider',help=argparse.SUPPRESS)
    ap.add_argument('--since',help='Skip document crawls checked at or after this ISO timestamp')
    args=ap.parse_args(argv)
    if args.provider: ap.error('External LLM providers are disabled; use scripts/prepare_luna_queue.py')
    if not 1<=args.workers<=8:ap.error('workers must be between 1 and 8')
    docs_path=ROOT/'data/admission-documents.jsonl';result_path=ROOT/'data/admission-results.jsonl'
    docs=load(docs_path);results=load(result_path)
    selected=[p for p in profiles() if not args.domains or p['domain'] in args.domains.split(',')]
    selected=selected[:args.limit or None]
    if args.stage in ('crawl','all'):
        cache_dir=ROOT/'data/cache/admission';cache_dir.mkdir(parents=True,exist_ok=True)
        pending=[p for p in selected if (args.refresh or p['domain'] not in docs) and (not args.since or docs.get(p['domain'],{}).get('checked_at','')<args.since)]
        print('Scanning admission pages:',len(pending),flush=True)
        with docs_path.open('a',encoding='utf8') as f,ThreadPoolExecutor(max_workers=args.workers) as pool:
            for i,future in enumerate(as_completed([pool.submit(crawl,p,cache_dir) for p in pending]),1):
                row=future.result();docs[row['key']]=row
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                print(f"[{i}/{len(pending)}] {row['key']} {row['status']} {len(row['documents'])} documents",flush=True)
    # `extract` is now only a deterministic recheck. Actual new interpretation is
    # performed by internal Luna and applied separately.
    if args.stage in ('extract','all'):
        pending=[docs[p['domain']] for p in selected if p['domain'] in docs and
                 (args.refresh or p['domain'] not in results or docs[p['domain']]['checked_at']>results[p['domain']].get('checked_at',''))]
        print('Revalidating known admission facts:',len(pending),flush=True)
        with result_path.open('a',encoding='utf8') as f:
            for i,doc in enumerate(pending,1):
                row=validate_known(doc,results.get(doc['key'],{}));results[row['key']]=row
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                print(f"[{i}/{len(pending)}] {row['key']} {row['status']} tariffs {len(row['tickets'])} free rules {len(row['free_rules'])}",flush=True)
    print('Admission sources cached:',len(docs),'revalidated:',len(results),flush=True)

if __name__=='__main__':main()
