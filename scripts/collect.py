"""Resumable per-domain website crawl and per-channel public Telegram collection."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.http_client import fetch
from src.services.site_extract import extract
from src.services.telegram_client import get_posts
ROOT = Path(__file__).resolve().parents[1]

def now():
    return datetime.now(timezone.utc).isoformat()
def load_cache(path):
    result = {}
    if path.exists():
        for line in path.read_text(encoding='utf8').splitlines():
            try:
                row = json.loads(line)
                result[row['key']] = row
            except ValueError:
                pass
    return result
def crawl(item):
    domain, url = item
    result = {'key': domain, 'url': url, 'checked_at': now(), 'pages': [], 'errors': [], 'events': [],
              'emails': [], 'phones': [], 'telegram': [], 'agenda': [], 'news': []}
    try:
        html, final = fetch(url)
        main = extract(html, final)
        pages = list(dict.fromkeys(main['contacts_pages'][:1] + main['agenda'][:2] + main['news'][:1]))[:3]
        def merge(data, source):
            result['pages'].append(source)
            for field in ('emails', 'phones', 'telegram', 'agenda', 'news'):
                result[field] = list(dict.fromkeys(result[field] + data[field]))
            result['events'].extend(data['events'])
        merge(main, final)
        for page in pages:
            if page == final:
                continue
            time.sleep(0.4)
            try:
                content, source = fetch(page)
                merge(extract(content, source), source)
            except Exception as exc:
                result['errors'].append({'url': page, 'error': str(exc)})
    except Exception as exc:
        result['errors'].append({'url': url, 'error': str(exc)})
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='0 = all domains')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--telegram-limit', type=int, default=0, help='0 = all known channels')
    ap.add_argument('--section',choices=['all','sites','telegram'],default='all')
    ap.add_argument('--no-build',action='store_true')
    ap.add_argument('--since',help='Skip rows checked at or after this ISO timestamp')
    args = ap.parse_args()
    museums = json.loads((ROOT/'data/museums.json').read_text(encoding='utf8'))
    domains = {}
    for m in museums:
        for url in m['sites']:
            domain = urlparse(url).hostname
            if domain:
                domains.setdefault(domain.removeprefix('www.'), url)
    selected = list(domains.items())[:args.limit or None]
    cache_path = ROOT/'data/site-results.jsonl'
    previous_sites=load_cache(cache_path)
    cache = dict(previous_sites)
    if args.section=='telegram':selected=[]
    with cache_path.open('a', encoding='utf8') as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(crawl, item) for item in selected if (args.refresh or item[0] not in cache) and (not args.since or cache.get(item[0],{}).get('checked_at','')<args.since)]
        for count,future in enumerate(as_completed(futures),1):
            row = future.result()
            old=previous_sites.get(row['key'])
            if not row['pages'] and old and old['pages']:
                for field in ('pages','events','emails','phones','telegram','agenda','news'):row[field]=old[field]
                row['stale']=True
                row['last_success_at']=old.get('last_success_at',old['checked_at'])
            else:row['last_success_at']=row['checked_at'] if row['pages'] else ''
            cache[row['key']] = row
            output.write(json.dumps(row, ensure_ascii=False) + '\n'); output.flush()
            print(f"sites {count}/{len(futures)}: {row['key']} ({len(row['pages'])} pages)", flush=True)
    channels = set()
    for m in museums:
        channels.update(c.lower() for c in m['telegram'])
    for row in cache.values():
        channels.update(c.lower() for c in row['telegram'])
    tg_path = ROOT/'data/telegram-results.jsonl'
    tg_cache = {k.lower():v for k,v in sorted(load_cache(tg_path).items(),key=lambda item:item[1].get('checked_at',''))}
    if args.section=='sites':channels=set()
    def channel_job(channel):
        row = {'key': channel, 'checked_at': now(), 'posts': [], 'error': ''}
        try:
            row['posts'] = get_posts(channel)
        except Exception as exc:
            row['error'] = str(exc)
            old=tg_cache.get(channel)
            if old and old['posts']:
                row['posts']=old['posts'];row['stale']=True
                row['last_success_at']=old.get('last_success_at',old['checked_at'])
        if not row['error']:row['last_success_at']=row['checked_at']
        return row
    with tg_path.open('a', encoding='utf8') as output, ThreadPoolExecutor(max_workers=min(args.workers, 4)) as pool:
        futures = [pool.submit(channel_job, c) for c in sorted(channels)[:args.telegram_limit or None] if (args.refresh or c not in tg_cache) and (not args.since or tg_cache.get(c,{}).get('checked_at','')<args.since)]
        for count,future in enumerate(as_completed(futures),1):
            row = future.result(); tg_cache[row['key']] = row
            output.write(json.dumps(row, ensure_ascii=False) + '\n'); output.flush()
            print(f"telegram {count}/{len(futures)}: {row['key']} ({len(row['posts'])} posts)", flush=True)
    if not args.no_build:
        from build_data import build
        build()
if __name__ == '__main__':
    main()
