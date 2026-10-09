"""Publish collected facts to a static JSON bundle, retain original source links."""
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.classify import classify, THEMES, OTHER
ROOT = Path(__file__).resolve().parents[1]
def cache(name):
    p = ROOT/'data'/name
    return {r['key']: r for r in map(json.loads, p.read_text(encoding='utf8').splitlines())} if p.exists() else {}
def build():
    museums = json.loads((ROOT/'data/museums.json').read_text(encoding='utf8'))
    overrides = json.loads((ROOT/'data/theme-overrides.json').read_text(encoding='utf8'))
    sites, telegram = cache('site-results.jsonl'), cache('telegram-results.jsonl')
    domains = {urlparse(u).hostname.removeprefix('www.') for m in museums for u in m['sites']}
    sites = {k: v for k, v in sites.items() if k in domains}
    canonical_telegram = {}
    for url, row in telegram.items():
        key = url.lower()
        if key not in canonical_telegram or row['posts']:
            row = dict(row)
            row['posts'] = [dict(p, channel=key) for p in row['posts']]
            canonical_telegram[key] = row
    telegram = canonical_telegram
    events, channels = {}, {}
    for m in museums:
        m['themes'] = overrides.get(m['id']) or classify(m['name'])
        m['theme_source'] = 'Ручная классификация' if m['id'] in overrides else 'Предварительно по названию'
        m['agenda'], m['news'], m['checked_at'], m['website_errors'] = [], [], '', []
        for url in m['sites']:
            r = sites.get(urlparse(url).hostname.removeprefix('www.'))
            if not r:
                continue
            m['checked_at'] = r['checked_at']
            m['website_errors'].extend(r['errors'])
            if r['pages']:
                m['verification'] = 'Сайт доступен; запись музея требует проверки'
            for field in ('emails', 'phones', 'telegram', 'agenda', 'news'):
                m[field] = list(dict.fromkeys(m[field] + r[field]))
            for event in r['events']:
                key = (urlparse(event['source']).hostname.removeprefix('www.') + '|' + event['start']
                       + '|' + event.get('end', '') + '|' + event['title'].strip().casefold())
                if key not in events:
                    e = dict(event)
                    e.update({'id': hashlib.sha256(key.encode()).hexdigest()[:12], 'museum_ids': [],
                              'kind': 'Лекция' if 'лекц' in e['title'].lower() else 'Экскурсия' if 'экскурс' in e['title'].lower() else 'Событие',
                              'checked_at': r['checked_at'], 'venue_note': 'Событие общего сайта. Конкретную площадку уточняйте в источнике.'})
                    events[key] = e
                elif len(urlparse(event['source']).path) > len(urlparse(events[key]['source']).path):
                    events[key]['source'] = event['source']
                    events[key]['url'] = event['url']
                if m['id'] not in events[key]['museum_ids']:
                    events[key]['museum_ids'].append(m['id'])
        for c in m['telegram']:
            c = c.lower()
            channels.setdefault(c, {'url': c, 'museum_ids': [], 'posts': [], 'error': 'Ещё не проверен', 'checked_at': ''})['museum_ids'].append(m['id'])
        m['telegram'] = list(dict.fromkeys(c.lower() for c in m['telegram']))
    for c, row in channels.items():
        if c in telegram:
            row.update({k: telegram[c][k] for k in ('posts', 'error', 'checked_at')})
    meta = json.loads((ROOT/'data/import-report.json').read_text(encoding='utf8'))
    meta.update({'built_at': datetime.now(timezone.utc).isoformat(), 'site_domains_total': len({urlparse(u).hostname.removeprefix('www.') for m in museums for u in m['sites']}),
                 'site_domains_checked': len(sites), 'site_domains_available': sum(bool(r['pages']) for r in sites.values()),
                 'channels': len(channels), 'channels_checked': sum(c in telegram for c in channels), 'channels_available': sum(bool(r['posts']) for r in channels.values()),
                 'events': len(events), 'posts': sum(len(r['posts']) for r in channels.values()),
                 'event_source_domains': len({urlparse(e['source']).hostname.removeprefix('www.') for e in events.values()}),
                 'with_telegram': sum(bool(m['telegram']) for m in museums)})
    payload = {'meta': meta, 'themes': [label for label, _ in THEMES] + [OTHER], 'museums': museums, 'events': sorted(events.values(), key=lambda e: e['start']), 'channels': list(channels.values())}
    dest = ROOT/'web/data'; dest.mkdir(parents=True, exist_ok=True)
    (dest/'catalog.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
    with (dest/'museums.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['name', 'address', 'category', 'themes', 'theme_source', 'sites', 'telegram', 'emails', 'phones', 'lat', 'lon', 'verification']
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=';'); writer.writeheader()
        for m in museums:
            writer.writerow({k: ', '.join(m[k]) if isinstance(m[k], list) else m[k] for k in fields})
    (ROOT/'data/collection-report.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(meta, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    build()
