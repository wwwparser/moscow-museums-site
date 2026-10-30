"""Source material for short, venue-specific exhibition notes. No LLM API access."""
import hashlib
import re
from urllib.parse import urljoin,urlparse
from bs4 import BeautifulSoup

def domain(url):
    return (urlparse(url).hostname or '').removeprefix('www.')

def clean(value):
    return re.sub(r'\s+',' ',str(value)).strip()

def extract_page(html,url,limit=11000):
    soup=BeautifulSoup(html,'html.parser')
    links=[]
    for a in soup.select('a[href]'):
        target=urljoin(url,a['href']);label=clean(a.get_text(' ',strip=True))
        if domain(target)!=domain(url) or urlparse(target).scheme not in ('https','http'):continue
        if re.search(r'\.(?:pdf|jpg|png|zip)(?:\?|$)',target,re.I):continue
        score=0
        text=(label+' '+urlparse(target).path).lower()
        if re.search(r'экспозиц|коллекц|экспонат|permanent|collection|exposition',text):score+=8
        if re.search(r'о музе|о нас|истори[яи] музе|about|history|muzej|museum',text):score+=4
        if re.search(r'новост|афиш|расписан|news|events|tickets|shop|privacy|contact|vk\.com',text):score-=12
        if score>0 and target.split('#')[0]!=url.split('#')[0]:links.append((score,target.split('#')[0],label))
    title=clean(soup.title.get_text()) if soup.title else ''
    for node in soup.select('script,style,noscript,nav,footer,header,form,svg,iframe'):
        node.decompose()
    root=soup.select_one('main') or soup.select_one('article') or soup.body or soup
    blocks=[]
    for node in root.select('h1,h2,h3,p,li'):
        text=clean(node.get_text(' ',strip=True))
        if len(text)<35 or len(text)>2300:continue
        if text not in blocks:blocks.append(text)
    if sum(map(len,blocks))<300:
        blocks=[clean(t) for t in root.get_text('\n',strip=True).splitlines() if len(clean(t))>=35]
    def rank(text):
        score=len(re.findall(r'экспозиц|экспонат|коллекци|подлин|мемориал|интерьер|воссозда|располож|здани|представлен|собрани|рукопис|можно увидеть|демонстрир|посвящ',text,re.I))
        if re.search(r'cookie|политик.*данн|купить билет|пользовательск.*соглаш|подпис',text,re.I):score-=10
        return score
    selected=sorted(range(len(blocks)),key=lambda i:(-rank(blocks[i]),i))
    keep=set();size=0
    for i in selected:
        if size+len(blocks[i])>limit:continue
        keep.add(i);size+=len(blocks[i])+1
    text='\n'.join(b for i,b in enumerate(blocks) if i in keep)
    return {'source':url,'title':title,'text':text,'links':list(dict.fromkeys(u for _,u,_ in sorted(links,reverse=True)))}

def fingerprint(documents):
    return hashlib.sha256('\n'.join(d['source']+'\n'+d['text'] for d in documents).encode()).hexdigest()
