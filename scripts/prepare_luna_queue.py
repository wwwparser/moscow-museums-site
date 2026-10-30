"""Create a local, source-backed queue for internal Luna review."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.admission_collector import excerpt
from src.services.admission_evidence import evidence_fingerprint
ROOT=Path(__file__).resolve().parents[1]

def load(path):
    return {r['key']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())} if path.exists() else {}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='data/luna-queue.json');args=ap.parse_args(argv)
    docs=load(ROOT/'data/admission-documents.jsonl');results=load(ROOT/'data/admission-results.jsonl')
    queue=[]
    for key,doc in docs.items():
        old=results.get(key,{})
        texts=[];raw_documents=[]
        for item in doc.get('documents',[]):
            try:text=Path(item['file']).read_text(encoding='utf8')
            except OSError:continue
            raw_documents.append({'source':item['source'],'text':text})
            texts.append({'source':item['source'],'kind':item.get('kind'),'text':excerpt(text,24000)})
        # Luna reviews evidence, so network failures without readable source text
        # cannot form a useful task. They remain visible in the normal update report.
        if not texts:continue
        current_hash=evidence_fingerprint(raw_documents)
        reviewed_at=old.get('luna_checked_at') or (old.get('checked_at','') if old.get('processor')=='internal-luna' else '')
        if old.get('processor')=='internal-luna':
            if old.get('evidence_hash'):
                evidence_changed=current_hash!=old['evidence_hash']
            else:
                evidence_changed=not reviewed_at or doc.get('checked_at','')>reviewed_at
            needs=bool(old.get('needs_luna_review') or evidence_changed or
                       old.get('status')=='extraction_error' or old.get('rejected') or
                       (old.get('input_truncated') and not old.get('review_complete')))
        else:
            needs=True
        if not needs:continue
        queue.append({'key':key,'name':doc.get('name'),'checked_at':doc.get('checked_at'),'status':doc.get('status'),
                      'errors':doc.get('errors',[]),'pages':doc.get('pages',[]),'previous':old,
                      'documents':texts,'evidence_hash':current_hash,'needs_luna_review':True,'processor':'internal-luna','task':'Extract admission tickets and free-entry rules, quote exact source evidence. Return JSON fields tickets and free_rules.'})
    output=(ROOT/args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'processor':'internal-luna','pending_luna':len(queue),'items':queue}
    tmp=output.with_suffix(output.suffix+'.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(output)
    print(json.dumps({'queue':str(output),'pending_luna':len(queue)},ensure_ascii=False))
if __name__=='__main__':main()
