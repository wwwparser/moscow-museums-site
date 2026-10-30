"""Capture all existing user flows for the explicitly requested ChatGPT redesign."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/redesign'
OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1280,'height':900},device_scale_factor=1)
    page.goto('https://wwwparser.github.io/moscow-museums-site/#catalog',wait_until='networkidle')
    page.wait_for_selector('.museum-card')
    page.screenshot(path=str(OUT/'before-catalog-desktop-first.png'))
    page.screenshot(path=str(OUT/'before-catalog-desktop-full.png'),full_page=True)
    for route in ('catalog','map','events','admission','telegram','sources'):
        page.locator(f'[data-tab="{route}"]').click()
        if route=='map':page.wait_for_timeout(2200)
        if route=='admission':page.locator('.admission-card summary').first.click()
        page.locator('#'+route).evaluate('(el)=>el.scrollIntoView({block:"start"})')
        page.screenshot(path=str(OUT/f'reference-{route}.png'))
    page.locator('[data-tab="catalog"]').click()
    page.locator('[data-museum]').first.click()
    page.screenshot(path=str(OUT/'reference-museum-detail.png'))
    page.locator('#close-dialog').click()
    page.set_viewport_size({'width':360,'height':800})
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(OUT/'before-catalog-mobile-first.png'))
    page.screenshot(path=str(OUT/'before-catalog-mobile-full.png'),full_page=True)
    page.locator('#catalog').evaluate('(el)=>el.scrollIntoView({block:"start"})')
    page.screenshot(path=str(OUT/'reference-mobile-catalog.png'))
    (OUT/'reference-meta.json').write_text(json.dumps({'url':'https://wwwparser.github.io/moscow-museums-site/','routes':['catalog','map','events','admission','telegram','sources','museum-detail'],'desktop':[1280,900],'mobile':[360,800]},indent=2),encoding='utf8')
    browser.close()
print('Captured 6 sections, museum detail and mobile reference')
