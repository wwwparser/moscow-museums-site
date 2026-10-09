"""Revalidate all published candidates against current local official-page snapshots."""
import json
from datetime import date
from pathlib import Path
from collect_admission import ROOT,load
from src.services.admission_extract import validate
from src.services.event_dates import parse_date_field

docs=load(ROOT/'data/admission-documents.jsonl');rows=load(ROOT/'data/admission-results.jsonl')
path=ROOT/'data/admission-results.jsonl'
with path.open('a',encoding='utf8') as output:
    for key,row in rows.items():
        if not row.get('tickets') and not row.get('free_rules'):continue
        documents=[{'source':d['source'],'text':Path(d['file']).read_text(encoding='utf8')} for d in docs[key]['documents']]
        # Multiple HTML/API representations of one URL are all source evidence.
        combined={}
        for d in documents:combined[d['source']]=combined.get(d['source'],'')+'\n'+d['text']
        candidates=row.get('candidates') or {k:row[k] for k in ('tickets','free_rules')}
        checked=validate(candidates,[{'source':u,'text':text} for u,text in combined.items()])
        row.update(checked)
        for rule in row['free_rules']:
            if rule['rule_type']=='dated_event':
                dates=parse_date_field(rule.get('when',''),allow_inferred_year=False)
                if dates and max((r.get('end') or r['start'])[:10] for r in dates)<date.today().isoformat():rule['past_date']=True
        if row.get('tickets') or row.get('free_rules'):
            row['status']='partial' if row['rejected'] or row.get('input_truncated') or row.get('errors') or row.get('stale') else 'facts_found'
        else:row['status']='no_admission_facts'
        output.write(json.dumps(row,ensure_ascii=False)+'\n')
print('Audited admission evidence for',len(rows),'sources')
