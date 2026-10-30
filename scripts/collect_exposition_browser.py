"""Bounded public Chrome fallback for readable exposition pages missing from HTTP crawl."""
import argparse,asyncio,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.exposition import domain,extract_page,fingerprint
from src.services.http_client import public_url
ROOT=Path(__file__).resolve().parents[1]

async def main():
    from playwright.async_api import async_playwright
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=0);args=ap.parse_args()
    path=ROOT/'data/exposition-documents.jsonl'
    rows={r['key']:r for r in map(json.loads,path.read_text(encoding='utf8').splitlines())}
    selected=[r for r in rows.values() if (not r['documents'] or r.get('stale')) and not r.get('browser_attempted')]
    # Process venue domains before portals and shared government/school sites.
    selected.sort(key=lambda r:(len(r['museums'])>5,not any('музей' in m['name'].lower() for m in r['museums']),r['key']))
    selected=selected[:args.limit or None];semaphore=asyncio.Semaphore(3)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True)
        async def job(row):
            async with semaphore:
                context=await browser.new_context(accept_downloads=False);page=await context.new_page()
                seeds=[u for m in row['museums'] for u in m['sites'] if domain(u)==row['key']]
                pages=[];errors=[];pending=seeds[:1];seen=set()
                for _ in range(2):
                    if not pending:break
                    url=pending.pop(0)
                    if url in seen:continue
                    seen.add(url)
                    try:
                        public_url(url)
                        response=await page.goto(url,wait_until='domcontentloaded',timeout=10000)
                        await page.wait_for_timeout(700)
                        if response and response.status>=400:raise ValueError('HTTP '+str(response.status))
                        if domain(page.url)!=row['key']:raise ValueError('Different-domain redirect')
                        doc=extract_page(await page.content(),page.url,11000)
                        if len(doc['text'])>=120:pages.append({k:doc[k] for k in ('source','title','text')})
                        pending.extend(doc['links'][:1])
                    except Exception as exc:errors.append({'url':url,'error':str(exc)[:200]})
                await context.close()
                new=dict(row,browser_attempted=True,browser_checked_at=datetime.now(timezone.utc).isoformat(),browser_errors=errors)
                if pages:
                    new.update(documents=pages,status='ready',checked_at=new['browser_checked_at'],last_success_at=new['browser_checked_at'],evidence_hash=fingerprint(pages),method='public-browser',stale=False)
                with path.open('a',encoding='utf8') as output:output.write(json.dumps(new,ensure_ascii=False)+'\n')
                (ROOT/'data/cache/exposition'/(row['key']+'.json')).write_text(json.dumps(new,ensure_ascii=False,indent=2),encoding='utf8')
                print('browser exposition:',row['key'],len(pages),'pages',flush=True)
        await asyncio.gather(*(job(r) for r in selected));await browser.close()
    print('Browser fallback completed:',len(selected),flush=True)
if __name__=='__main__':asyncio.run(main())
