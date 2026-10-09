"""Retry rows that need evidence review after improving the extraction validator."""
from collect_admission import main,load,ROOT
rows=load(ROOT/'data/admission-results.jsonl')
selected=[k for k,r in rows.items() if r.get('rejected') or r.get('status')=='extraction_error']
print('Refining sources with rejected evidence:',len(selected),flush=True)
if selected:main(['--stage','extract','--refresh','--domains',','.join(selected),'--workers','4'])
