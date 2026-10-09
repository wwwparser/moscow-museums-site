"""Bounded per-source crawl; snapshots and diffs are persisted by the CLI."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import time
from urllib.parse import urldefrag, urlparse, urljoin
from bs4 import BeautifulSoup
from .http_client import fetch
from .event_adapters import parse_page, tretyakov, ajax_pages
from .site_extract import http_url

def event_identity(e):
    # Title is needed for a calendar page with multiple events sharing one URL/time.
    url=urldefrag(e['url'])[0]
    return hashlib.sha256((url+'|'+e['title'].strip().casefold()+'|'+e['start']).encode()).hexdigest()[:16]

def normalize_events(events,reference,days,domain):
    result={};until=(reference+timedelta(days=days)).isoformat()
    for e in events:
        if not e.get('start') or not e.get('title'):continue
        end=(e.get('end') or e['start'])[:10]
        if end<reference.isoformat() or e['start'][:10]>until:continue
        if e.get('end') and e['end'][:10]<e['start'][:10]:continue
        e=dict(e);e['source_site']=domain;e['monitor_id']=event_identity(e)
        e.setdefault('schedule_type','period' if end!=e['start'][:10] else 'session' if e.get('date_precision')=='time' else 'day')
        e.setdefault('year_inferred',False);e.setdefault('venue','');e.setdefault('date_text',e['start'])
        result[e['monitor_id']]=e
    # Keep exact sessions instead of a second untimed placeholder for the same title/day.
    timed={(e['url'],e['title'],e['start'][:10]) for e in result.values() if e['date_precision']=='time'}
    selected=[e for e in result.values() if e['date_precision']=='time' or (e['url'],e['title'],e['start'][:10]) not in timed]
    grouped={};single=[]
    for e in selected:
        if e['date_precision']=='day' and not e.get('end'):
            grouped.setdefault((e['url'],e['title']),[]).append(e)
        else:single.append(e)
    for rows in grouped.values():
        if len(rows)==1:single.extend(rows);continue
        rows.sort(key=lambda e:e['start']);e=dict(rows[0])
        e['occurrence_dates']=sorted({r['start'][:10] for r in rows})
        e['end']=rows[-1]['start'];e['schedule_type']='listed-days'
        single.append(e)
    return sorted(single,key=lambda e:e['start'])

def discover_links(html,base,profile):
    soup=BeautifulSoup(html,'html.parser');pagination=[];lists=[];details=[]
    host=urlparse(base).hostname
    for a in soup.select('a[href]'):
        url=urldefrag(http_url(a['href'],base))[0]
        if not url or urlparse(url).hostname!=host:continue
        path=urlparse(url).path
        if re.search(r'archive|/news|/blog|/collection|/kollek|tickets|/policy',url,re.I):continue
        if a.get('id')=='ajax_next_page' or re.search(r'PAGEN_\d+=\d+|/page/\d+',url):pagination.append(url)
        elif re.search(r'/(?:events?|afisha|calendar|poster|shows|playbill)/?$',path):lists.append(url)
        elif re.search(r'/(?:events?|afisha|poster|shows|recital|lectures|exhibitions|concerts)/[^/]+',path):details.append(url)
    return [*dict.fromkeys(pagination)], [*dict.fromkeys(lists)], [*dict.fromkeys(details)]

def monitor(profile,days=90,previous=None):
    reference=date.today();domain=profile['domain'];now=datetime.now(timezone.utc).isoformat()
    row={'key':domain,'name':profile['name'],'adapter':profile.get('adapter','generic'),'checked_at':now,
         'status':'needs_adapter','pages':[],'errors':[],'events':[],'horizon_days':days,
         'coverage':'Индивидуальный адаптер' if profile.get('adapter')!='generic' else 'Общий поиск дат; адаптер требует проверки',
         'changes':{'added':0,'removed':0,'changed':0},'stale':False}
    events=[];mode=profile.get('adapter','generic')
    try:
        if mode=='tretyakov-api':
            events,sources=tretyakov(fetch,reference,days);row['pages']=sources
        elif mode in ('scriabin','pushkin'):
            html,url=ajax_pages(fetch,profile,reference,days);row['pages'].append(url)
            events=parse_page(html,url,profile,reference)
        else:
            queue=list(dict.fromkeys(profile.get('seeds',[])));visited=set();details_used=0
            limit=profile.get('max_pages',4)
            while queue and len(visited)<limit:
                url=queue.pop(0)
                if url in visited:continue
                visited.add(url);time.sleep(0.25)
                try:
                    html,final=fetch(url);row['pages'].append(final)
                    events.extend(parse_page(html,final,profile,reference))
                    next_pages,lists,details=discover_links(html,final,profile)
                    queue.extend(u for u in next_pages+lists if u not in visited and u not in queue)
                    if details_used<profile.get('max_details',0):
                        for u in details[:profile['max_details']-details_used]:
                            if u not in visited and u not in queue:queue.append(u);details_used+=1
                except Exception as exc:row['errors'].append({'url':url,'error':str(exc)})
        row['events']=normalize_events(events,reference,days,domain)
        row['status']='ok' if row['events'] else 'no_dates' if row['pages'] and mode!='generic' else 'needs_adapter' if row['pages'] else 'unavailable'
        if row['errors'] and row['events']:row['status']='partial'
    except Exception as exc:
        row['errors'].append({'url':profile.get('seeds',[''])[0],'error':str(exc)})
        row['status']='unavailable'
    old={e['monitor_id']:e for e in (previous or {}).get('events',[])}
    new={e['monitor_id']:e for e in row['events']}
    if row['errors'] and previous and previous.get('events'):
        for key,e in old.items():
            if key not in new and (e.get('end') or e['start'])[:10]>=reference.isoformat():
                row['events'].append(dict(e,stale=True));row['stale']=True
    row['changes']['added']=len(set(new)-set(old))
    # Disappearance is an observation, not proof of cancellation. Partial/error scans cannot prove it.
    row['changes']['removed']=len(set(old)-set(new)) if not row['errors'] else 0
    row['changes']['changed']=sum(new[k]!=old[k] for k in set(new)&set(old))
    return row
