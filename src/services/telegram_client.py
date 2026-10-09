"""Read the latest five available public posts, without a user session."""
from bs4 import BeautifulSoup
from .http_client import fetch

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
        posts.append({'id': ident, 'channel': channel, 'url': 'https://t.me/' + ident,
                      'text': text.get_text('\n', strip=True) if text else 'Медиа-публикация — открыть в Telegram',
                      'date': time['datetime']})
    if not posts:
        raise ValueError('Public channel preview unavailable or empty')
    return posts[-5:]
