"""Extract published contact links, agenda links and schema.org dated events."""
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

def http_url(value, base=''):
    if not isinstance(value, str):
        return ''
    url = urljoin(base, value.strip())
    parsed = urlparse(url)
    return url if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username else ''

def channel_url(value):
    url = http_url(value)
    p = urlparse(url)
    if p.hostname not in ('t.me', 'telegram.me'):
        return ''
    name = p.path.strip('/').removeprefix('s/').split('/')[0]
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{3,31}', name) or name in ('share', 'joinchat', 'iv'):
        return ''
    return 'https://t.me/' + name.lower()

def date_value(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).isoformat()
    except (ValueError, TypeError):
        return ''

def extract(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    result = {'emails': [], 'phones': [], 'telegram': [], 'agenda': [], 'news': [], 'contacts_pages': [], 'events': []}
    for a in soup.select('a[href]'):
        href = a.get('href', '').strip()
        label = a.get_text(' ', strip=True)
        if href.startswith('mailto:'):
            email = href[7:].split('?')[0]
            if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                result['emails'].append(email)
        elif href.startswith('tel:'):
            result['phones'].append(href[4:])
        url = http_url(href, base)
        if not url:
            continue
        tg = channel_url(url)
        if tg:
            result['telegram'].append(tg)
        if urlparse(url).hostname != urlparse(base).hostname:
            continue
        text = (label + ' ' + urlparse(url).path).lower()
        for field, pattern in [('agenda', r'афиш|расписан|календар|лекци|экскурс|afisha|events|calendar'),
                               ('news', r'новост|news'), ('contacts_pages', r'контакт|contacts')]:
            if re.search(pattern, text):
                result[field].append(url)
    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            typ = node.get('@type', [])
            types = typ if isinstance(typ, list) else [typ]
            if any(str(t).endswith('Event') for t in types):
                start = date_value(node.get('startDate'))
                end = date_value(node.get('endDate'))
                if start and node.get('name'):
                    name = BeautifulSoup(str(node['name']), 'html.parser').get_text(' ', strip=True)
                    result['events'].append({'title': name, 'start': start, 'end': end,
                        'url': http_url(node.get('url', ''), base) or base,
                        'source': base, 'status': node.get('eventStatus', ''), 'date_precision': 'day' if len(str(node.get('startDate'))) == 10 else 'time'})
            for child in node.values():
                if isinstance(child, (dict, list)):
                    walk(child)
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(tag.string or tag.get_text()))
        except (ValueError, TypeError):
            pass
    for field in result:
        if field != 'events':
            result[field] = list(dict.fromkeys(result[field]))
    return result
