"""Keep Moscow city and Zelenograd. Preserve branches and every raw source."""
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.services.site_extract import http_url, channel_url

ROOT = Path(__file__).resolve().parents[1]
def norm(s):
    return re.sub(r'[^а-яa-z0-9]', '', (s or '').lower().replace('ё', 'е'))
def urls(value):
    return list(dict.fromkeys(re.findall(r'https?://[^\s,;]+', value or '')))
def number(value):
    try:
        return float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        return None
def main():
    rows = [json.loads(s) for s in (ROOT/'data/raw/museums.jsonl').read_text(encoding='utf8').splitlines()]
    merged = {}
    excluded = []
    for row in rows:
        rubric = row.get('Подрубрика') or row.get('Рубрика') or ''
        if not re.search(r'музе', rubric, re.I):
            excluded.append(row)
            continue
        if row.get('Город') not in ('Москва', 'Зеленоград') and not (not row.get('Город') and row.get('Регион') == 'Москва'):
            excluded.append(row)
            continue
        name, address = row.get('Название') or '', row.get('Адрес') or ''
        clean_address = re.sub(r'\b(москва|россия|город|г|ул|улица)\b', '', address.lower())
        clean_address = re.sub(r'\b(стр|строение)\b', 'ст', clean_address)
        clean_address = re.sub(r'\b(корп|корпус)\b', 'к', clean_address)
        key = norm(name.split(',')[0]) + '|' + norm(clean_address)
        if not address:
            key += '|' + norm(row.get('Сайт'))
        sites = [u for u in urls(row.get('Сайт')) if not channel_url(u) and 'vk.com' not in u]
        tg = [channel_url(u) for u in urls((row.get('telegram') or '') + ' ' + (row.get('Сайт') or ''))]
        lat, lon = number(row.get('Широта')), number(row.get('Долгота'))
        if lat is None or lon is None or not (55.1 <= lat <= 56.2 and 36.5 <= lon <= 38.3):
            lat = lon = None
        category = 'Музеи-квартиры' if re.search('квартир|дом-музей|дом музей', name, re.I) else 'Музеи'
        new = {'id': hashlib.sha256(key.encode()).hexdigest()[:12], 'name': name, 'address': address,
               'city': row.get('Город') or 'Москва', 'category': category, 'sites': sites,
               'telegram': [u for u in tg if u], 'emails': [x.strip() for x in (row.get('Email') or '').split(',') if x.strip()],
               'phones': [x.strip() for x in (row.get('Телефон') or '').split(',') if x.strip()],
               'hours': row.get('Время работы') or '', 'lat': lat, 'lon': lon,
               'sources': [{'engine': row['__engine'], 'file': row['__source']}], 'verification': 'Справочник: актуальность не проверена'}
        if key not in merged:
            merged[key] = new
        else:
            old = merged[key]
            for field in ('sites', 'telegram', 'emails', 'phones'):
                old[field] = list(dict.fromkeys(old[field] + new[field]))
            if new['sources'][0] not in old['sources']:
                old['sources'] += new['sources']
            if old['lat'] is None and lat is not None:
                old['lat'], old['lon'] = lat, lon
    museums = sorted(merged.values(), key=lambda m: m['name'].lower())
    (ROOT/'data/museums.json').write_text(json.dumps(museums, ensure_ascii=False, indent=2), encoding='utf8')
    (ROOT/'data/raw/excluded.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in excluded), encoding='utf8')
    meta = {'imported_at': datetime.now(timezone.utc).isoformat(), 'raw_rows': len(rows), 'excluded_rows': len(excluded),
            'museums': len(museums), 'with_site': sum(bool(m['sites']) for m in museums),
            'with_coordinates': sum(m['lat'] is not None for m in museums), 'with_telegram': sum(bool(m['telegram']) for m in museums),
            'note': 'Каталог кандидатов из локальных выгрузок, дата исходных данных неизвестна. Возможны дубли и закрытые площадки.'}
    (ROOT/'data/import-report.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(meta, ensure_ascii=False))
if __name__ == '__main__':
    main()
