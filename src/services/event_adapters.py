"""Individual site selectors and API adapters, with a conservative generic fallback."""
from datetime import date, datetime, timedelta, timezone
import json
import re
from urllib.parse import urljoin, urlparse, urlencode
from bs4 import BeautifulSoup
from .event_dates import parse_date_field
from .site_extract import extract, http_url

def kind(text):
    text=text.lower()
    for pattern,label in [(r'экскурс|tour','Экскурсия'),(r'лекц|лектор|lecture','Лекция'),
                          (r'мастер.класс|workshop','Мастер-класс'),(r'выстав|exhibition','Выставка'),
                          (r'концерт|concert','Концерт'),(r'спектак|theatre','Спектакль'),(r'кино|film','Кинопоказ')]:
        if re.search(pattern,text):return label
    return 'Событие'

def event(title,url,source,dates,venue='',category=''):
    title=BeautifulSoup(title,'html.parser').get_text(' ',strip=True)
    return [dict(d,title=title,url=http_url(url,source) or source,source=source,status='',
                 kind=kind(category+' '+title),venue=venue,parser='site-adapter') for d in dates if title]

def selector_cards(html,source,profile,reference):
    soup=BeautifulSoup(html,'html.parser');result=[];rules=profile.get('rules',[])
    for rule in rules:
        for card in soup.select(rule['card']):
            title_node=card.select_one(rule['title']) if rule.get('title') else card
            if not title_node:continue
            title=title_node.get_text(' ',strip=True)
            url_node=card if card.name=='a' else card.select_one(rule.get('link','a[href]'))
            if not url_node or not url_node.get('href'):url_node=card.find_parent('a',href=True)
            url=url_node.get('href',source) if url_node else source
            fields=[card.select_one(selector) for selector in rule['date']]
            raw=' '.join(n.get('datetime') or n.get(rule.get('date_attr','')) or n.get_text(' ',strip=True) for n in fields if n)
            if rule.get('aria_date'):
                n=card.select_one(rule['aria_date']);raw=n.get('aria-label','') if n else raw
            venue_node=card.select_one(rule['venue']) if rule.get('venue') else None
            category_node=card.select_one(rule['kind']) if rule.get('kind') else None
            dates=parse_date_field(raw,reference,rule.get('infer_year',False),rule.get('date_list',False))
            if rule.get('force_period') and len(dates)==2:
                dates=[dict(dates[0],end=dates[1]['start'],schedule_type='period')]
            # An end-only label is the closing date of a programme, not a single session.
            if re.match(r'^\s*до\b',raw,re.I):
                stamp=card.get(rule.get('start_unix_attr',''))
                if stamp and dates:
                    try:
                        start=datetime.fromtimestamp(int(stamp),timezone(timedelta(hours=3))).date().isoformat()
                        dates=[dict(dates[0],start=start,end=dates[0]['start'][:10],date_precision='day',schedule_type='period')]
                    except (ValueError,OverflowError,OSError):dates=[]
                else:dates=[]
            result.extend(event(title,url,source,dates,venue_node.get_text(' ',strip=True) if venue_node else '',category_node.get_text(' ',strip=True) if category_node else rule.get('category','')))
    return result

def bulgakov(html,source,reference):
    soup=BeautifulSoup(html,'html.parser');result=[]
    for node in soup.select('[data-agenda-day][data-agenda-day-entries]'):
        raw=node['data-agenda-day'];dates=parse_date_field(raw,reference)
        try:entries=json.loads(node['data-agenda-day-entries'])
        except ValueError:continue
        for row in entries:
            venue={'nehoroshaya-kvartira':'Большая Садовая, 10 («Нехорошая квартира»)',
                   'bolshaya-pirogovskaya':'Большая Пироговская, 35А'}.get(row.get('venueSlug'),'')
            result.extend(event(row.get('title',''),row.get('href',''),source,dates,venue,row.get('label','')))
    # Schedule rows in the day list expose exact tour times independently of the monthly overview.
    for section in soup.select('[id^="agenda-day-"]'):
        day=section.get('id','').removeprefix('agenda-day-')
        for card in section.select('article'):
            title=card.select_one('h2 a,h3 a')
            if not title:continue
            text=card.get_text(' ',strip=True)
            times=re.findall(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b',text)
            for time in times:
                result.extend(event(title.get_text(' ',strip=True),title.get('href',source),source,
                                    parse_date_field(day+'T'+time,reference)))
    return result

def mec_calendar(html,source,reference):
    soup=BeautifulSoup(html,'html.parser');result=[]
    for section in soup.select('[data-mec-cell]'):
        raw=section['data-mec-cell']
        if not re.fullmatch(r'\d{8}',raw):continue
        day=f'{raw[:4]}-{raw[4:6]}-{raw[6:]}'
        for card in section.select('.mec-event-article'):
            title=card.select_one('.mec-event-title a');time=card.select_one('.mec-event-time')
            if not title:continue
            times=re.findall(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b',time.get_text(' ',strip=True) if time else '')
            dates=parse_date_field(day+('T'+times[0] if times else ''),reference)
            if len(times)>1 and dates:
                dates[0]['end']=day+'T'+times[1]+'+03:00'
            venue=card.select_one('.mec-event-loc-place')
            result.extend(event(title.get_text(' ',strip=True),title.get('href'),source,dates,
                                venue.get_text(' ',strip=True) if venue else ''))
    return result

def generic(html,source,reference):
    """Require date + informative event link in the same small card; never news dates."""
    soup=BeautifulSoup(html,'html.parser');result=extract(html,source)['events']
    for a in soup.select('a[href]'):
        url=http_url(a['href'],source);p=urlparse(url)
        if not url or p.hostname!=urlparse(source).hostname:continue
        if re.search(r'/news|/novost|/blog|/press|/archive/(?:20[0-2]\d)',p.path,re.I):continue
        if not re.search(r'/(?:events?|afisha|poster|recital|playbill|shows|exhibitions?|lectures?|excursions?|concerts?|sobytiya|meropriyatiya)(?:/[^/#?]+)',p.path,re.I):continue
        if a.find_parent(['nav','header','footer']):continue
        title=a.get_text(' ',strip=True)
        if len(title)<8 or len(title)>250 or re.search(r'^(подробнее|купить|билеты|читать)',title,re.I):continue
        card=a
        for _ in range(5):
            if card is None or card.name in ('body','html'):break
            # An ancestor containing multiple event titles is a list, not one event.
            if len(card.get_text(' ',strip=True))>1600:break
            nodes=card.select('time[datetime], [class*="date"], [class*="interval"], [class*="period"]')
            nodes=[n for n in nodes if n.name not in ('script','style') and len(n.get_text(' ',strip=True))<200]
            dates=[]
            for n in nodes:
                raw=n.get('datetime') or n.get_text(' ',strip=True)
                dates.extend(parse_date_field(raw,reference,False))
            if dates:
                result.extend(event(title,url,source,dates));break
            card=card.parent
    return result

def parse_page(html,source,profile,reference):
    mode=profile.get('adapter','generic')
    if mode=='bulgakov':return bulgakov(html,source,reference)
    if mode=='mec-calendar':return mec_calendar(html,source,reference)
    if profile.get('rules'):return selector_cards(html,source,profile,reference)
    return generic(html,source,reference)

def tretyakov(fetch_page,reference,days):
    result=[];sources=[]
    root='https://www.tretyakovgallery.ru'
    sections=['lektsii','spetsialnye-meropriyatiya','kontserty-i-spektakli-events','tvorcheskie-zanyatiya','vstrechi-1','dlya-druzey-muzeya']
    for section in sections:
        for page in range(1,5):
            url=root+'/api/content/events/?'+urlencode({'section':section,'page':page,'page_size':100,'archive':'n','lang':'ru'})
            text,final=fetch_page(url,content_types=('json',));sources.append(final)
            obj=json.loads(text);items=obj.get('data',{}).get('items',[])
            for row in items:
                dates=parse_date_field(row.get('startDate',''),reference)
                if not dates and row.get('startDateUnix'):
                    dt=datetime.fromtimestamp(int(row['startDateUnix']),timezone(timedelta(hours=3)))
                    dates=parse_date_field(dt.isoformat(),reference)
                if dates and row.get('endDate'):
                    ends=parse_date_field(row['endDate'],reference)
                    if ends:dates[0]['end']=ends[-1]['start'];dates[0]['schedule_type']='period' if dates[0]['start'][:10]!=ends[-1]['start'][:10] else 'session'
                if not dates:continue
                place=row.get('place') or {}
                result.extend(event(row.get('name',''),row.get('url',''),final,dates,place.get('name',''),row.get('hashtag','')))
            total=obj.get('data',{}).get('pagination',{});count=total.get('totalPages') if isinstance(total,dict) else None
            if not items or len(items)<100 or (count and page>=int(count)):break
    return result,sources

def ajax_pages(fetch_page,profile,reference,days):
    mode=profile['adapter']
    if mode=='scriabin':
        url='https://scriabinmuseum.ru/wp-admin/admin-ajax.php';payload={'action':'load_all_events','date':'all'}
    else:
        end=reference+timedelta(days=days)
        url='https://pushkinmuseum.art/events/blocks/events_query.php'
        payload={'filter':'','day0':reference.day,'month0':reference.month-1,'year0':reference.year,
                 'day1':end.day,'month1':end.month-1,'year1':end.year,'needless_buildings':'','categories':'369,370,696,22069,699,17104,19624,22525,23365,23981',
                 'show_categories_list':'0','lang':'ru','layout':'slider'}
    content,final=fetch_page(url,method='POST',data=payload,content_types=('html','json'))
    if content.lstrip().startswith('{'):
        obj=json.loads(content)
        body=obj.get('data',obj.get('html',''))
        if isinstance(body,dict):body=body.get('html',body.get('content',''))
        if isinstance(body,str):content=body
    return content,final
