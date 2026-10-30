"""Verify source-backed exposition notes on cards, details, search and mobile."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/expositions';OUT.mkdir(parents=True,exist_ok=True)
result={'checks':[],'errors':[],'http_errors':[]}
def check(name,condition):
    result['checks'].append({'name':name,'pass':bool(condition)})
    assert condition,name
with sync_playwright() as p:
    b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1280,'height':1000})
    page.on('pageerror',lambda e:result['errors'].append(str(e)))
    page.on('response',lambda r:result['http_errors'].append({'url':r.url,'status':r.status}) if r.status>=400 else None)
    page.goto('http://127.0.0.1:8768/#catalog');page.wait_for_selector('.museum-card')
    page.locator('#search').fill('Бункер');page.evaluate('document.fonts.ready')
    check('Bunker descriptions present',page.locator('.museum-card .exposition-note').count()>=4)
    check('cards show supported depth', '65 метров' in page.locator('#museum-list').inner_text() and '43 метров' in page.locator('#museum-list').inner_text())
    check('source links',page.locator('.exposition-note a[href^="https://bunker"]').count()>=4)
    page.locator('#exposition-only').check();check('only described museum filter',page.locator('.exposition-missing').count()==0)
    page.locator('#exposition-only').uncheck()
    page.locator('#catalog').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'bunkers-desktop.png'),full_page=True)
    page.locator('[data-museum="64eda5ce64da"]').click();check('detail has same exposition',page.locator('#museum-detail .exposition-note').count()==1)
    check('detail mentions siren','сирен' in page.locator('#museum-detail .exposition-note').inner_text())
    page.screenshot(path=str(OUT/'bunker703-detail-desktop.png'));page.keyboard.press('Escape')
    page.locator('#search').fill('сирену');check('search finds an exhibit',page.locator('#museum-list').inner_text().find('Бункер-703')>=0)
    page.locator('#search').fill('Бункер')
    page.set_viewport_size({'width':360,'height':800});page.screenshot(path=str(OUT/'bunkers-mobile-full.png'),full_page=True)
    page.locator('.exposition-note').first.scroll_into_view_if_needed();page.screenshot(path=str(OUT/'exposition-mobile.png'))
    check('no mobile page overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    check('card text is not clamped',page.locator('.exposition-note p').first.evaluate('(e)=>e.scrollHeight<=e.clientHeight+1'))
    page.locator('#search').fill('ГБОУ СОШ № 1421');check('missing description is honest',page.locator('.exposition-missing').count()>0)
    page.locator('#search').fill('Бункер');page.set_viewport_size({'width':1280,'height':1000})
    check('no unsafe sources',page.locator('.exposition-sources a').evaluate_all('(xs)=>xs.every(x=>/^https?:/.test(x.href)&&x.rel.includes("noopener"))'))
    check('no browser errors',not result['errors']);check('no HTTP errors',not result['http_errors'])
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'checks':len(result['checks']),'errors':result['errors']},ensure_ascii=False));b.close()
