"""Validate Luna's factual notes against captured source text before publishing."""
import argparse,json,re,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.exposition import clean,domain
ROOT=Path(__file__).resolve().parents[1]

def validate_record(record,row,evidence,museums):
    ids=record.get('museum_ids',[])
    if not ids or any(i not in museums for i in ids):raise ValueError('Unknown museum ID')
    if record.get('scope')!='venue':raise ValueError('Only venue-specific facts are publishable')
    for mid in ids:
        if row['key'] not in [domain(u) for u in museums[mid]['sites']]:raise ValueError('Museum does not belong to source')
    facts=record.get('facts',[])
    if not 2<=len(facts)<=4:raise ValueError('Need 2–4 distinct supported facts')
    seen=set();accepted=[]
    for fact in facts:
        text=clean(fact.get('text',''));quote=clean(fact.get('quote',''));source=fact.get('source','')
        if not 25<=len(text)<=340 or '?'*3 in text:raise ValueError('Invalid fact length/encoding')
        if len(quote)<18 or len(quote)>500:raise ValueError('Invalid evidence length')
        if domain(source)!=row['key']:raise ValueError('Source belongs to a different domain')
        if source not in evidence or quote.casefold().replace('ё','е') not in clean(evidence[source]).casefold().replace('ё','е'):
            raise ValueError('Quote not present in captured source: '+source+' :: '+quote[:100])
        if text in seen:raise ValueError('Duplicate fact')
        seen.add(text);accepted.append({'text':text,'source':source})
    if sum(len(f['text']) for f in accepted)>1000:raise ValueError('Description too long for a card')
    return ids,accepted

def load_evidence(rows):
    docs={}
    for row in rows.values():
        for doc in row.get('documents',[]):docs.setdefault(doc['source'],'');docs[doc['source']]+='\n'+doc['text']
    manual=ROOT/'data/cache/exposition/manual/index.json'
    if manual.exists():
        for item in json.loads(manual.read_text(encoding='utf8')):
            docs.setdefault(item['source'],'');docs[item['source']]+='\n'+(manual.parent/item['file']).read_text(encoding='utf8')
    for path in (ROOT/'data/cache/exposition').glob('extra-*.json'):
        obj=json.loads(path.read_text(encoding='utf8'));items=obj.get('documents',[]) if isinstance(obj,dict) else obj
        for item in items:docs.setdefault(item['source'],'');docs[item['source']]+='\n'+item['text']
    return docs

def read_results(path):
    # Accept concatenated JSON objects from interrupted append jobs as well as JSONL.
    # Every object is still decoded and validated; malformed data is never skipped.
    text=path.read_text(encoding='utf8');decoder=json.JSONDecoder();position=0
    while position<len(text):
        while position<len(text) and text[position].isspace():position+=1
        if position==len(text):break
        if text.startswith('\\n',position):position+=2;continue
        row,end=decoder.raw_decode(text,position)
        yield text.count('\n',0,position)+1,row
        position=end

def freshness(note,current):
    if current.get('stale'):return 'stale'
    if current.get('evidence_hash') and current['evidence_hash']!=note.get('evidence_hash'):return 'stale'
    if current and not current.get('documents'):
        last_attempt=max(current.get('checked_at',''),current.get('browser_checked_at',''))
        if last_attempt[:10]>note.get('checked_at','')[:10]:return 'stale'
    return 'verified'

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--strict',action='store_true');args=ap.parse_args(argv)
    docs_path=ROOT/'data/exposition-documents.jsonl'
    history=list(map(json.loads,docs_path.read_text(encoding='utf8').splitlines())) if docs_path.exists() else []
    rows={r['key']:r for r in history}
    hashes={}
    for doc in history:hashes.setdefault(doc['key'],set()).add(doc['evidence_hash'])
    evidence=load_evidence(rows);museums={m['id']:m for m in json.loads((ROOT/'data/museums.json').read_text(encoding='utf8'))}
    dest=ROOT/'data/exposition-notes.json'
    output=json.loads(dest.read_text(encoding='utf8')) if dest.exists() else {'museums':{},'reviews':{}}
    invalid=[];accepted=0
    files=[ROOT/'data/exposition-manual.jsonl',*sorted((ROOT/'data').glob('exposition-luna-*.jsonl')),*sorted((ROOT/'data').glob('exposition-curated*.jsonl'))]
    for path in files:
        if not path.exists():continue
        latest={}
        for n,row in read_results(path):latest[row['key']]=(n,row)
        for n,row in latest.values():
            try:
                if row.get('processor')!='internal-luna':raise ValueError('Only internal Luna results allowed')
                if row['key'] not in rows:raise ValueError('Unknown source key')
                if row.get('evidence_hash') and row['evidence_hash'] not in hashes[row['key']]:raise ValueError('Unrecognized evidence hash')
                current=rows.get(row['key'],{});records=[]
                reviewed_at=datetime.fromisoformat(row['checked_at'].replace('Z','+00:00'))
                if reviewed_at.tzinfo is None:raise ValueError('Review timestamp needs a timezone')
                recorded_at=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)
                checked_at=min(reviewed_at,recorded_at).isoformat()
                for record in row.get('records',[]):
                    if len(record.get('facts',[]))<2 and record.get('status',row.get('status')) in ('insufficient','not_museum'):continue
                    records.append(validate_record(record,row,evidence,museums))
                targets={mid for ids,_ in records for mid in ids}
                if not row.get('append_records'):
                    for mid,note in list(output['museums'].items()):
                        if note['domain']==row['key'] and mid not in targets and note.get('evidence_hash')==(row.get('evidence_hash') or current.get('evidence_hash')):
                            del output['museums'][mid]
                for ids,facts in records:
                    for mid in ids:
                        output['museums'][mid]={'facts':facts,'checked_at':checked_at,'domain':row['key'],'processor':'internal-luna','evidence_hash':row.get('evidence_hash') or current.get('evidence_hash',''),'status':'verified'}
                        accepted+=1
                output['reviews'][row['key']]={'evidence_hash':row.get('evidence_hash') or current.get('evidence_hash',''),'status':row.get('status','ok' if records else 'insufficient'),'checked_at':checked_at,'note':row.get('note','')}
            except (ValueError,KeyError) as exc:invalid.append({'file':path.name,'line':n,'key':row.get('key'),'error':str(exc)})
    # A new crawl does not silently make a previously written description fresh.
    for note in output['museums'].values():
        current=rows.get(note['domain'],{})
        note['status']=freshness(note,current)
    output['updated_at']=datetime.now(timezone.utc).isoformat()
    tmp=dest.with_suffix('.json.tmp');tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(dest)
    report={'museums_with_notes':len(output['museums']),'reviewed_domains':len(output['reviews']),'accepted_records':accepted,'invalid':invalid}
    path=ROOT/'artifacts/exposition-validation.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False)[:9000])
    if args.strict and invalid:raise SystemExit(1)
if __name__=='__main__':main()
