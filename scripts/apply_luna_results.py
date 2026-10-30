"""Validate internal Luna output against the current official snapshots."""
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.admission_extract import validate
from src.services.admission_evidence import evidence_fingerprint
ROOT=Path(__file__).resolve().parents[1]

def load(path):
    return {r['key']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())} if path.exists() else {}

def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()] if path.exists() else []

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--input',default='data/luna-results.jsonl');ap.add_argument('--output',default='data/admission-results.jsonl');args=ap.parse_args(argv)
    docs=load(ROOT/'data/admission-documents.jsonl');results=load(ROOT/args.output)
    accepted=0;rejected=0
    output=ROOT/args.output
    with output.open('a',encoding='utf8') as f:
        for candidate in records(ROOT/args.input):
            if not isinstance(candidate,dict) or not all(isinstance(candidate.get(field,[]),list) for field in ('tickets','free_rules')):
                rejected+=1;continue
            key=candidate.get('key');doc=docs.get(key)
            if candidate.get('processor')!='internal-luna' or not doc or candidate.get('checked_at')!=doc.get('checked_at'):
                rejected+=1;continue
            previous=results.get(key,{})
            if doc.get('errors') and not doc.get('documents'):
                row=dict(previous);row.update(key=key,checked_at=doc.get('checked_at'),status='stale',stale=True,
                    last_success_at=previous.get('last_success_at') or previous.get('checked_at'),last_attempt_at=doc.get('checked_at'),
                    errors=doc.get('errors'),processor='internal-luna')
                if not previous.get('tickets') and not previous.get('free_rules'):
                    row.update(tickets=[],free_rules=[],status='unavailable',stale=False,last_success_at=None)
            else:
                texts=[]
                for item in doc.get('documents',[]):
                    try:texts.append({'source':item['source'],'text':Path(item['file']).read_text(encoding='utf8')})
                    except OSError:pass
                combined={}
                for item in texts:combined[item['source']]=combined.get(item['source'],'')+'\n'+item['text']
                if not combined and (previous.get('tickets') or previous.get('free_rules')):
                    row=dict(previous);row.update(key=key,checked_at=doc.get('checked_at'),status='stale',stale=True,
                        last_success_at=previous.get('last_success_at') or previous.get('checked_at'),last_attempt_at=doc.get('checked_at'),processor='internal-luna')
                else:
                    proposed={field:candidate.get(field,[]) for field in ('tickets','free_rules')}
                    # Include prior candidates, so previously verified facts remain if Luna
                    # omitted them; all are checked against the same current documents.
                    # Carry forward only facts that were previously accepted, never
                    # rejected raw candidates from an older review.
                    prior={field:previous.get(field,[]) for field in ('tickets','free_rules')}
                    if candidate.get('replace_previous'):
                        if not candidate.get('replacement_reason'):raise ValueError('Replacing previous facts requires an internal Luna explanation')
                        prior={field:[] for field in prior}
                    merged={field:[*proposed[field],*prior.get(field,[])] for field in proposed}
                    checked=validate(merged,[{'source':u,'text':t} for u,t in combined.items()])
                    row={k:doc.get(k) for k in ('key','name','checked_at','pages','errors','links','status')}
                    row.update(checked,candidates=merged,processor='internal-luna',input_truncated=bool(candidate.get('input_truncated')))
                    row['luna_checked_at']=candidate['checked_at']
                    if combined:
                        row['evidence_hash']=evidence_fingerprint(texts)
                    row['review_complete']=bool(candidate.get('review_complete'))
                    row['review_exclusions']=candidate.get('rejected',[])
                    row['needs_luna_review']=bool(candidate.get('needs_luna_review') or ((row['rejected'] or row['input_truncated']) and not row['review_complete']))
                    row['status']='partial' if row['rejected'] or row['errors'] or row['input_truncated'] else 'facts_found' if row['tickets'] or row['free_rules'] else 'no_admission_facts'
                    row['last_success_at']=doc.get('checked_at') if row['tickets'] or row['free_rules'] else previous.get('last_success_at')
            results[key]=row;f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();accepted+=1
    print(json.dumps({'accepted':accepted,'rejected':rejected,'total':len(records(ROOT/args.input))},ensure_ascii=False))
if __name__=='__main__':main()
