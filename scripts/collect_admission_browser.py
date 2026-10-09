"""Render explicitly configured public tariff pages when the HTTP page is only an app shell."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from src.services.http_client import public_url
from src.services.admission_collector import text_page,PRICE
from collect_admission import profiles,load,ROOT

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--domains',required=True);args=ap.parse_args()
    rows={p['domain']:p for p in profiles()};path=ROOT/'data/admission-documents.jsonl';cache=load(path)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        try:
            with path.open('a',encoding='utf8') as out:
                for domain in args.domains.split(','):
                    profile=rows[domain];old=cache.get(domain,{})
                    row=dict(old,key=domain,name=profile['name'],checked_at=datetime.now(timezone.utc).isoformat(),documents=list(old.get('documents',[])),pages=list(old.get('pages',[])),errors=[])
                    for address in profile.get('browser_seeds',[]):
                        public_url(address);page=browser.new_page()
                        try:
                            page.goto(address,wait_until='networkidle',timeout=30000)
                            text=text_page(page.content());final=page.url;public_url(final)
                            row['pages'].append(final)
                            if not PRICE.search(text) and 'бесплатн' not in text.casefold():continue
                            ident=hashlib.sha256(final.encode()).hexdigest()[:16];dest=ROOT/'data/cache/admission'/(domain+'-browser-'+ident+'.txt')
                            dest.write_text(text,encoding='utf8');row['documents']=[d for d in row['documents'] if d['source']!=final]
                            row['documents'].append({'source':final,'file':str(dest),'kind':'rendered-html','text_chars':len(text),'excerpt_chars':min(len(text),24000),'truncated':len(text)>24000})
                            print(domain,'rendered',final,len(text),flush=True)
                        except Exception as exc:row['errors'].append({'url':address,'error':str(exc)})
                        finally:page.close()
                    row['pages']=list(dict.fromkeys(row['pages']));row['status']='documents_found' if row['documents'] else 'not_found'
                    out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
        finally:browser.close()

if __name__=='__main__':main()
