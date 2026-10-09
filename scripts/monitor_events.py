"""Refresh per-site agendas independently from contacts/Telegram, with resume and history."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.event_monitor import monitor
ROOT=Path(__file__).resolve().parents[1]

def load(path):
    return {r['key']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())} if path.exists() else {}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workers',type=int,default=6)
    ap.add_argument('--days',type=int,default=90)
    ap.add_argument('--domains',help='Comma-separated source domains')
    ap.add_argument('--dedicated-only',action='store_true')
    ap.add_argument('--refresh',action='store_true',help='Bypass per-source refresh interval')
    args=ap.parse_args()
    if args.workers<1 or args.workers>8:ap.error('workers must be between 1 and 8')
    if not 1<=args.days<=366:ap.error('days must be between 1 and 366')
    profiles=json.loads((ROOT/'data/event-profiles.json').read_text(encoding='utf8'))
    path=ROOT/'data/event-results.jsonl';cache=load(path)
    selected=[];now=datetime.now(timezone.utc)
    for domain,profile in profiles.items():
        if not profile.get('enabled',True):continue
        if args.domains and domain not in args.domains.split(','):continue
        if args.dedicated_only and profile['adapter']=='generic':continue
        prev=cache.get(domain)
        if prev and not args.refresh:
            age=(now-datetime.fromisoformat(prev['checked_at'])).total_seconds()/3600
            if age<profile.get('refresh_hours',12):continue
        selected.append(profile)
    print(f'Monitoring {len(selected)} sources for {args.days} days',flush=True)
    history=ROOT/'data/event-history.jsonl'
    with path.open('a',encoding='utf8') as output, history.open('a',encoding='utf8') as changes,ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(monitor,p,args.days,cache.get(p['domain'])) for p in selected]
        for i,future in enumerate(as_completed(futures),1):
            row=future.result();cache[row['key']]=row
            output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
            changes.write(json.dumps({k:row[k] for k in ('key','checked_at','status','changes')},ensure_ascii=False)+'\n');changes.flush()
            print(f"[{i}/{len(selected)}] {row['key']} {row['status']} {len(row['events'])} events",flush=True)
    from build_data import build
    build()
if __name__=='__main__':main()
