"""Find admission/pricing pages on public museum sites, preserving source snapshots."""
from datetime import datetime,timezone
from io import BytesIO
import hashlib
import re
import time
from urllib.parse import urlparse,urldefrag,urlunparse,parse_qsl,urlencode
from bs4 import BeautifulSoup
from .http_client import fetch
from .site_extract import http_url

PRICE=re.compile(r'\b\d[\d\s\u00a0]{0,8}\s*(?:руб(?:\.|лей|ля|ль)?|₽|р\.)',re.I)
SIGNAL=re.compile(r'стоимост|тариф|цен[аыу]|бесплатн|льгот|прейскурант|пенсионер|многодет|инвалид|студент|ветеран|школьник',re.I)
LINK=re.compile(r'билет|стоимост|тариф|прейскурант|льгот|бесплатн|посещен|посетител|спланировать|ticket|price|pricing|visitor|benefit|admission|/visit(?:/|$)',re.I)
STRONG=re.compile(r'стоимост|тариф|прейскурант|льгот|бесплатн|price|pricing|benefit|admission|lgot|free|stoim',re.I)

def canonical(url):
    p=urlparse(url);netloc=p.netloc.removesuffix(':443').removesuffix(':80')
    query=urlencode([(k,v) for k,v in parse_qsl(p.query) if k not in ('special','lang','LANG','utm_source','utm_campaign')])
    return urlunparse((p.scheme,netloc,p.path.rstrip('/') or '/',p.params,query,''))

def text_page(html):
    soup=BeautifulSoup(html,'html.parser')
    for n in soup.select('script,style,noscript,nav,footer,form'):n.decompose()
    # Exhibition layouts can put their tariff in a content header. Keep those;
    # remove only navigation headers without actual admission facts.
    for n in soup.select('header'):
        if not PRICE.search(n.get_text(' ',strip=True)) and not re.search(r'бесплатн\w* (?:вход|посещ)|вход[^.]{0,40}свободн',n.get_text(' ',strip=True),re.I):n.decompose()
    for br in soup.select('br'):br.replace_with('\n')
    lines=[re.sub(r'\s+',' ',s).strip() for s in soup.get_text('\n').splitlines()]
    return '\n'.join(s for s in lines if s)

def excerpt(text,max_chars=24000):
    """Keep surrounding tariff table/category text rather than isolated numbers."""
    if len(text)<=max_chars:return text
    windows=[]
    for m in SIGNAL.finditer(text):
        start=max(0,m.start()-700);end=min(len(text),m.end()+1700)
        if windows and start<=windows[-1][1]:windows[-1]=(windows[-1][0],max(end,windows[-1][1]))
        else:windows.append((start,end))
    parts=[];remaining=max_chars
    for a,b in windows:
        part=text[a:b][:remaining];parts.append(part);remaining-=len(part)
        if remaining<=0:break
    return '\n[…]\n'.join(parts)

def pricing_links(html,base,domain):
    soup=BeautifulSoup(html,'html.parser');links={}
    for a in soup.select('a[href]'):
        u=urldefrag(http_url(a['href'],base))[0]
        if not u:continue
        host=urlparse(u).hostname or ''
        if host.removeprefix('www.')!=domain and host!=urlparse(base).hostname:continue
        label=a.get_text(' ',strip=True)+' '+u
        if not LINK.search(label):continue
        if re.search(r'/news/|/events/[^/]+|/afisha/[^/]+|archive|policy|privacy|/en/|lang=en|[?&]special=|/=$',u,re.I):continue
        score=6 if STRONG.search(label) else 2 if re.search(r'билет|ticket',label,re.I) else 1
        if u.lower().endswith('.pdf'):score+=1
        links[u]=max(links.get(u,0),score)
    return sorted(links,key=lambda u:(-links[u],len(u)))

def read_document(url):
    content,final=fetch(url,content_types=('html','pdf','json'),raw=True,max_bytes=25_000_000)
    if '/api/' in urlparse(final).path:
        import json
        obj=json.loads(content)
        def values(value):
            if isinstance(value,dict):return '\n'.join(values(v) for v in value.values())
            if isinstance(value,list):return '\n'.join(values(v) for v in value)
            return value if isinstance(value,str) else ''
        return text_page(values(obj)),final,'json',''
    if content.startswith(b'%PDF'):
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(content))
        text='\n'.join(page.extract_text(extraction_mode='layout') or '' for page in reader.pages[:35])
        return text,final,'pdf',''
    # Decode HTML explicitly, preserving Russian content.
    try:html=content.decode('utf8')
    except UnicodeDecodeError:html=content.decode('windows-1251')
    return text_page(html),final,'html',html

def crawl(profile,cache_dir,max_pages=5):
    domain=profile['domain']
    row={'key':domain,'name':profile['name'],'checked_at':datetime.now(timezone.utc).isoformat(),
         'pages':[],'documents':[],'errors':[],'links':[],'status':'not_found'}
    queue=list(dict.fromkeys(profile['seeds']));visited=set();found_links=[];attempts=0
    max_pages=profile.get('max_pages',max_pages)
    while queue and attempts<max_pages:
        u=queue.pop(0)
        if canonical(u) in visited:continue
        visited.add(canonical(u));attempts+=1;time.sleep(.25)
        try:
            text,final,kind,html=read_document(u)
            public_source=profile.get('source_urls',{}).get(u,final)
            row['pages'].append(public_source)
            visited.add(canonical(final))
            if html:
                links=pricing_links(html,final,domain);found_links.extend(links)
                # Prioritise pricing/benefit pages over additional visitor landing pages.
                queue=list(dict.fromkeys([x for x in links if canonical(x) not in visited]+queue))
            if PRICE.search(text) or re.search(r'бесплатн|свободн\w* вход|вход[^\n.]{0,40}свободн',text,re.I):
                ident=hashlib.sha256(final.encode()).hexdigest()[:16]
                path=cache_dir/(domain.replace(':','_')+'-'+ident+'.txt')
                path.write_text(text,encoding='utf8')
                row['documents'].append({'source':public_source,'file':str(path),'kind':kind,'text_chars':len(text),
                                         'excerpt_chars':len(excerpt(text)),'truncated':len(text)>24000})
        except Exception as exc:row['errors'].append({'url':u,'error':str(exc)})
    row['links']=list(dict.fromkeys(found_links))
    row['status']='documents_found' if row['documents'] else 'not_found' if row['pages'] else 'unavailable'
    return row
