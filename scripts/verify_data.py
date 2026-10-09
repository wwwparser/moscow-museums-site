"""Validate referential integrity and uniqueness of the published bundle."""
import json
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
p = json.loads((ROOT/'web/data/catalog.json').read_text(encoding='utf8'))
ids = {m['id'] for m in p['museums']}
assert len(ids) == len(p['museums']), 'Duplicate museum IDs'
assert p['meta']['museums'] == len(p['museums'])
assert p['meta']['events'] == len(p['events'])
assert len({e['id'] for e in p['events']}) == len(p['events']), 'Duplicate event IDs'
for m in p['museums']:
    assert m['themes'] and set(m['themes']).issubset(p['themes']), m['name']
    assert m['sources'], m['name']
    if m['lat'] is not None:
        assert m['lon'] is not None and 55.1 <= m['lat'] <= 56.2 and 36.5 <= m['lon'] <= 38.3
for e in p['events']:
    assert set(e['museum_ids']).issubset(ids), e['id']
    assert e['source'].startswith(('http://', 'https://'))
    datetime.fromisoformat(e['start'])
    if e['end']:
        assert e['end'][:10] >= e['start'][:10], e['id']
post_ids = []
for c in p['channels']:
    assert set(c['museum_ids']).issubset(ids)
    assert len(c['posts']) <= 5
    post_ids.extend(x['id'].lower() for x in c['posts'])
assert len(post_ids) == len(set(post_ids)), 'Duplicate Telegram posts'
assert len(post_ids) == p['meta']['posts']
print(f"Verified: {len(ids)} museums, {len(p['events'])} dated events, {len(post_ids)} posts")
