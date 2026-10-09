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
    cache = {} if args.refresh else load_cache(cache_path)
    with cache_path.open('a', encoding='utf8') as output, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(crawl, item) for item in selected if item[0] not in cache]
        for future in as_completed(futures):
            row = future.result()
            cache[row['key']] = row
            output.write(json.dumps(row, ensure_ascii=False) + '\n'); output.flush()
            print(f"sites {len(cache)}/{len(domains)}: {row['key']} ({len(row['pages'])} pages)", flush=True)
    channels = set()
    for m in museums:
        channels.update(m['telegram'])
    for row in cache.values():
        channels.update(row['telegram'])
    tg_path = ROOT/'data/telegram-results.jsonl'
    tg_cache = {} if args.refresh else load_cache(tg_path)
    def channel_job(channel):
        row = {'key': channel, 'checked_at': now(), 'posts': [], 'error': ''}
        try:
            row['posts'] = get_posts(channel)
        except Exception as exc:
            row['error'] = str(exc)
        return row
    with tg_path.open('a', encoding='utf8') as output, ThreadPoolExecutor(max_workers=min(args.workers, 4)) as pool:
        futures = [pool.submit(channel_job, c) for c in sorted(channels)[:args.telegram_limit or None] if c not in tg_cache]
        for future in as_completed(futures):
            row = future.result(); tg_cache[row['key']] = row
            output.write(json.dumps(row, ensure_ascii=False) + '\n'); output.flush()
            print(f"telegram {len(tg_cache)}/{len(channels)}: {row['key']} ({len(row['posts'])} posts)", flush=True)
    from build_data import build
    build()
if __name__ == '__main__':
    main()
