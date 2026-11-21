"""Save Google AI overview leads using one named Browser Bridge tab."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path.home()/'.codex/skills/browser-bridge'))
import bridge

READ = r'''(() => {
  const headings = [...document.querySelectorAll('[role=heading],h1,h2,h3')];
  const heading = headings.find(x => /^(Обзор от ИИ|AI Overview)$/i.test(x.textContent.trim()));
  if (location.pathname.startsWith('/sorry') || document.querySelector('form#captcha-form, iframe[src*="recaptcha"]')) return {blocked: true};
  if (location.hostname !== 'www.google.com' || location.pathname !== '/search') return {blocked: true};
  if (!heading) return {overview: '', links: []};
  const block = heading.closest('[data-attrid]') || heading.closest('section') || heading.parentElement.parentElement.parentElement;
  return {overview: block.innerText.slice(0,10000), links: [...new Set([...block.querySelectorAll('a[href]')].map(a=>a.href))]};
})()'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='0 processes the full remaining queue')
    args = parser.parse_args()
    data = json.loads((ROOT/'web/data/catalog.json').read_text(encoding='utf8'))
    queue = [m for m in data['museums'] if not m.get('exposition')]
    queue.sort(key=lambda m: (m['id'] != 'e8284efdd44d', bool(m['sites']), m['name']))
    path = ROOT/'data/cache/exposition/google-overviews.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(line)['id'] for line in path.read_text(encoding='utf8').splitlines()} if path.exists() else set()
    bridge.set_session('museum-search')
    tab = bridge.tabinfo()
    current = urlsplit(tab.get('url') or '')
    if not tab.get('pinned') or current.hostname != 'www.google.com' or current.path != '/search':
        raise SystemExit('Pin a Google search in the museum-search Bridge session first')
    todo = [m for m in queue if m['id'] not in done][:args.limit or None]
    with path.open('a', encoding='utf8') as output:
        for index, museum in enumerate(todo, 1):
            query = museum['name']+' '+museum['address']
            address = 'https://www.google.com/search?'+urlencode({'q':query,'sourceid':'chrome','ie':'UTF-8','source':'chrome.ctxt'})
            navigation = bridge.cdp('Page.navigate', {'url':address})
            if not navigation.get('ok') or navigation.get('result', {}).get('errorText'):
                raise SystemExit('Search paused: Google navigation failed')
            time.sleep(random.uniform(6, 10))
            result = bridge.js_eval(READ)
            if not isinstance(result, dict) or result.get('_error') or result.get('blocked'):
                raise SystemExit('Search paused: Bridge unavailable or Google requested verification')
            output.write(json.dumps(dict(result, id=museum['id'], query=query,
                                         checked_at=datetime.now(timezone.utc).isoformat()), ensure_ascii=False)+'\n')
            output.flush()
            print(f'{index}/{len(todo)} {museum["id"]}: {len(result["overview"])} overview characters', flush=True)

if __name__ == '__main__':
    main()
