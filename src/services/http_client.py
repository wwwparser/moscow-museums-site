"""Bounded, retrying public-page requests; no authentication or secrets."""
import ipaddress
import socket
import time
from urllib.parse import urlparse
import requests

AGENT = 'MoscowMuseumPrototype/0.1 (+public museum directory)'

def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
        raise ValueError('Only public HTTP(S) URLs are allowed')
    for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise ValueError('Non-public address')
    return url

def fetch(url, content_types=('html',), method='GET', data=None):
    last = None
    for attempt in range(2):
        try:
            current = public_url(url)
            for _ in range(5):
                with requests.request(method, current, data=data, timeout=(5, 12), headers={'User-Agent': AGENT},
                                      allow_redirects=False, stream=True) as response:
                    if response.is_redirect:
                        from urllib.parse import urljoin
                        current = public_url(urljoin(current, response.headers['Location']))
                        continue
                    response.raise_for_status()
                    if not any(kind in response.headers.get('Content-Type', '').lower() for kind in content_types):
                        raise ValueError('Unexpected content type')
                    chunks = bytearray()
                    for part in response.iter_content(65536):
                        chunks.extend(part)
                        if len(chunks) > 3_000_000:
                            raise ValueError('Page exceeds size limit')
                    response._content = bytes(chunks)
                    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                        response.encoding = response.apparent_encoding
                    return response.text, current
            raise ValueError('Too many redirects')
        except (requests.RequestException, ValueError, OSError) as exc:
            last = exc
            if isinstance(exc, ValueError):
                break
            time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(str(last))
