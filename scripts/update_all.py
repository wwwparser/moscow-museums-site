"""One repeatable update with an OS lock, logs, validation and optional Pages publishing."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
GENERATED=['web/data/catalog.json','web/data/museums.csv','web/data/admission.csv','web/data/event-sources.csv','web/data/update-report.json','data/collection-report.json','data/event-profiles.json','data/exposition-notes.json']

@contextmanager
def update_lock():
    path=ROOT/'data/cache/update.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another update is already running')
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def cache(name):
    p=ROOT/'data'/name
    return {r['key']:r for r in map(json.loads,p.read_text(encoding='utf8').splitlines())} if p.exists() else {}

def report(started,mode,steps):
    sites,events,fees,tg=[cache(n) for n in ('site-results.jsonl','event-results.jsonl','admission-results.jsonl','telegram-results.jsonl')]
    catalog=json.loads((ROOT/'web/data/catalog.json').read_text(encoding='utf8'))
    domains={u for m in catalog['museums'] for u in m.get('admission_domains',[])}|{r['domain'] for r in catalog['event_sources']}
    def stats(rows,error_field):
        selected=list(rows.values());return {'checked':len(selected),'checked_today':sum(r.get('checked_at','').startswith(datetime.now(timezone.utc).date().isoformat()) for r in selected),'checked_this_run':sum(r.get('checked_at','')>=started for r in selected),'last_attempt_at':max((r.get('checked_at','') for r in selected),default=''),'stale':sum(bool(r.get('stale')) for r in selected),'with_errors':sum(bool(r.get(error_field) or r.get('extraction_error')) for r in selected)}
    queue_path=ROOT/'data/luna-queue.json'
    try:pending_luna=json.loads(queue_path.read_text(encoding='utf8')).get('pending_luna',0)
    except (OSError,ValueError):pending_luna=0
    exposition_summary_path=ROOT/'data/cache/exposition/summary.json'
    exposition_summary=json.loads(exposition_summary_path.read_text(encoding='utf8')) if exposition_summary_path.exists() else {}
    result={'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'mode':mode,'steps':steps,'pending_luna':pending_luna,'llm_processing':'internal-luna','external_llm_enabled':False,
        'sites':stats({k:v for k,v in sites.items() if k in domains},'errors'),'events':stats(events,'errors'),
        'admission':stats(fees,'errors'),'telegram':stats({c['url']:c for c in catalog['channels']},'error'),
        'expositions':exposition_summary,'pending_exposition_luna':exposition_summary.get('pending_luna',0),
        'counts':catalog['meta'],'status':'partial' if any(s['status']!='ok' for s in steps) else 'completed'}
    for section in ('sites','events','admission','telegram'):
        if result[section]['stale'] or result[section]['with_errors']:result['status']='partial'
    path=ROOT/'web/data/update-report.json';tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
    return result

def clean_source_tree():
    if subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip():raise RuntimeError('Commit or unstage pending changes before automated publishing')
    changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
    if any(name not in GENERATED for name in changed):raise RuntimeError('Source edits are pending; automated publishing stopped')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['auto','daily','full'],default='auto');ap.add_argument('--resume',action='store_true');ap.add_argument('--publish',action='store_true');ap.add_argument('--finish-only',action='store_true');args=ap.parse_args()
    mode=('full' if datetime.now().weekday()==6 else 'daily') if args.mode=='auto' else args.mode
    started=datetime.now(timezone.utc).isoformat();steps=[]
    if args.finish_only:
        today=datetime.now(timezone.utc).date().isoformat()
        attempts=[r.get('checked_at','') for name in ('site-results.jsonl','telegram-results.jsonl','event-results.jsonl','admission-documents.jsonl') for r in cache(name).values() if r.get('checked_at','').startswith(today)]
        if attempts:started=min(attempts)
    logs=ROOT/'artifacts/update-logs';logs.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONUNBUFFERED='1')
    with update_lock(),(logs/(datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')).open('w',encoding='utf8') as log:
        if args.publish:clean_source_tree()
        def run(name,command,required=True):
            print('STEP:',name,flush=True);log.write('\nSTEP: '+name+'\n');log.flush()
            with subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace') as proc:
                for line in proc.stdout:log.write(line);log.flush();print(line,end='',flush=True)
                code=proc.wait()
            steps.append({'name':name,'status':'ok' if code==0 else 'error','exit_code':code})
            if code and required:raise RuntimeError(name+' failed; see update log')
        py=sys.executable;since=['--since',datetime.now(timezone.utc).date().isoformat()] if args.resume else []
        try:
            if not args.finish_only:
                if mode=='full':run('sites and Telegram',[py,'scripts/collect.py','--refresh','--workers','8','--no-build',*since])
                else:run('Telegram',[py,'scripts/collect.py','--section','telegram','--refresh','--no-build',*since])
                run('event profiles',[py,'scripts/create_event_profiles.py'])
                run('events',[py,'scripts/monitor_events.py','--workers','8','--no-build',*([] if args.resume else ['--refresh'])])
                if mode=='full':
                    run('admission pages',[py,'scripts/collect_admission.py','--stage','crawl','--workers','8','--refresh',*since])
                    profiles=json.loads((ROOT/'data/admission-profiles.json').read_text(encoding='utf8'))
                    dynamic=','.join(k for k,v in profiles.items() if v.get('browser_seeds'))
                    if dynamic:run('rendered admission pages',[py,'scripts/collect_admission_browser.py','--domains',dynamic],required=False)
                    run('admission facts revalidation',[py,'scripts/collect_admission.py','--stage','extract','--workers','2'],required=False)
                    run('admission audit',[py,'scripts/audit_admission.py'])
                run('prepare internal Luna queue',[py,'scripts/prepare_luna_queue.py'],required=False)
                if mode=='full':
                    run('exposition source pages',[py,'scripts/collect_expositions.py','--workers','8',*([] if args.resume else ['--refresh'])],required=False)
                    run('rendered exposition pages',[py,'scripts/collect_exposition_browser.py'],required=False)
                run('validate exposition facts',[py,'scripts/apply_expositions.py'],required=False)
                run('prepare exposition Luna queue',[py,'scripts/collect_expositions.py','--prepare-only'],required=False)
            run('build',[py,'scripts/build_data.py']);run('verification',[py,'scripts/verify_data.py'])
            for file in ('app.js','telegram-feed.js','admission-view.js','update-status.js','exposition-view.js'):run(file,['node','--check','web/'+file])
            summary=report(started,mode,steps);print('UPDATE SUMMARY:',json.dumps({k:v for k,v in summary.items() if k not in ('counts','steps')},ensure_ascii=True),flush=True)
            if summary.get('pending_luna'):print(f"PENDING_LUNA: {summary['pending_luna']} sources require internal Luna review; the scheduled job does not process this queue.",flush=True)
            if args.publish:
                clean_source_tree();run('stage data',['git','add','--',*GENERATED])
                if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode:
                    run('commit data',['git','commit','-m','Refresh museum data '+datetime.now().date().isoformat()])
                run('publish',['powershell','-NoProfile','-File','scripts/publish.ps1'])
        except Exception:
            report(started,mode,steps);raise

if __name__=='__main__':main()
