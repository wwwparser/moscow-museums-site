"""Read the latest five available public posts, without a user session."""
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urlsplit
from .http_client import fetch


def post_body(node):
    if node is None:
        return 'Медиа-публикация — открыть в Telegram', []
    parts, links = [], []
    offset = 0
    for item in node.descendants:
        if type(item) is not NavigableString:
            continue
        value = str(item)
        anchor = item.find_parent('a', href=True)
        if anchor:
            href = anchor['href'].strip()
            try:
                parsed = urlsplit(href)
                if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username:
                    if links and links[-1]['end'] == offset and links[-1]['url'] == href:
                        links[-1]['end'] += len(value)
                    else:
                        links.append({'start': offset, 'end': offset+len(value), 'url': href})
            except ValueError:
                pass
        parts.append(value)
        offset += len(value)
    raw = ''.join(parts)
    leading = len(raw)-len(raw.lstrip())
    end = len(raw.rstrip())
    return raw.strip(), [dict(link, start=max(link['start'], leading)-leading,
                             end=min(link['end'], end)-leading)
                        for link in links if max(link['start'], leading)<min(link['end'], end)]

def get_posts(channel):
    name = channel.rsplit('/', 1)[-1]
    html, _ = fetch('https://t.me/s/' + name)
    soup = BeautifulSoup(html, 'html.parser')
    posts = []
    for node in soup.select('.tgme_widget_message[data-post]'):
        ident = node.get('data-post', '')
        text = node.select_one('.tgme_widget_message_text')
        time = node.select_one('time[datetime]')
        if not ident or not time:
            continue
        if text:
            for br in text.select('br'):br.replace_with('\n')
            for block in text.select('p,blockquote'):block.insert_before('\n');block.insert_after('\n')
        body, links = post_body(text)
        posts.append({'id': ident, 'channel': channel, 'url': 'https://t.me/' + ident,
                      'text': body, 'links': links,
                      'date': time['datetime']})
    if not posts:
        raise ValueError('Public channel preview unavailable or empty')
    return posts[-5:]
