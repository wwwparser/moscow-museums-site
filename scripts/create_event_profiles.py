"""Each catalog domain gets its own tracked monitor configuration."""
import json
from pathlib import Path
import re
from urllib.parse import urlparse, urldefrag
ROOT=Path(__file__).resolve().parents[1]

def rule(card,title,dates,**kwargs):
    return dict(card=card,title=title,date=dates,**kwargs)

CUSTOM={
 'tretyakovgallery.ru':{'adapter':'tretyakov-api','seeds':['https://www.tretyakovgallery.ru/events/']},
 'pushkinmuseum.art':{'adapter':'pushkin','seeds':['https://pushkinmuseum.art/events/index.php?lang=ru'],
                     'rules':[rule('.item--card','.font-gmtext',['.desc__date'],link='.desc a[href]',venue='.desc__place',kind='.desc__type',start_unix_attr='data-date')]},
 'scriabinmuseum.ru':{'adapter':'scriabin','seeds':['https://scriabinmuseum.ru/afisha/'],
                     'rules':[rule('.card_event','h3',['.date_and_time'],kind='.b_caption.top_left',venue='.b_caption.bottom_left',infer_year=True)]},
 'bulgakovmuseum.ru':{'adapter':'bulgakov','seeds':['https://bulgakovmuseum.ru/calendar']},
 'dombulgakova.ru':{'adapter':'mec-calendar','seeds':['https://dombulgakova.ru/kalendar/']},
 'jewish-museum.ru':{'adapter':'cards','seeds':['https://www.jewish-museum.ru/events/'],
                     'rules':[rule('.event-card','.event-card__name',['.event-card__date'],link='.event-card__name')]},
 'domgogolya.ru':{'adapter':'cards','seeds':['https://www.domgogolya.ru/events/'],
                     'rules':[rule('.event','.name-event',['.day-event .number','.day-event .month','.time-event'],venue='.where-event',kind='.format-event',infer_year=True)]},
 'mamm-mdf.ru':{'adapter':'cards','seeds':['https://mamm.art/events/'],
                     'rules':[rule('a.sched__row','.sched__title',['time'])]},
 'mosmuseum.ru':{'adapter':'cards','seeds':['https://mosmuseum.ru/'],
                     'rules':[rule('a:has(.interval)','h3',['.interval'],venue='.tag-place',kind='.tag-event-type',infer_year=True)]},
 'tsaritsyno-museum.ru':{'adapter':'cards','seeds':['https://tsaritsyno-museum.ru/events/'],
                     'rules':[rule('.card__wrap','.card__title',['.card__action'],kind='.card__tag',infer_year=True)]},
 'kosmo-museum.ru':{'adapter':'cards','seeds':['https://kosmo-museum.ru/events'],
                     'rules':[rule('.bricks-default_i','h3',['li:has(.ico__time)'],link='a.bricks-default_i_hover',kind='.bricks-default_i_cnt_section')]},
 'darwinmuseum.ru':{'adapter':'cards','seeds':['https://www.darwinmuseum.ru/'],
                     'rules':[rule('a.view_list.timetable-link','h3',['.view_list_date'],infer_year=True,date_list=True),
                              rule('.carousel-caption','h2 a',['p'],infer_year=True,date_list=True)]},
 'kuskovo.ru':{'adapter':'cards','seeds':['https://kuskovo.ru/','https://kuskovo.ru/our-events/concerts/'],
                     'rules':[rule('.concert__item-box','.concert__name',['.concert__date','.concert__day'],venue='.concert__info',category='Концерт',infer_year=True),
                              rule('a.exhibition__item','.exhibition__name',['.exhibition__date'],category='Выставка')]},
 'shm.ru':{'adapter':'cards','seeds':['https://shm.ru/shows/'],
                     'rules':[rule('.gim-card-event','.gim-h5',['.gim-card-event__date'],venue='.gim-card-event__museum',kind='.gim-card-event__type')]},
 'victorymuseum.ru':{'adapter':'cards','seeds':['https://victorymuseum.ru/playbill/events/'],
                     'rules':[rule('.oblique-items .item','.name',['.date'],link='.name',kind='.age-limit-box')]},
 'mmoma.ru':{'adapter':'cards','seeds':['https://mmoma.ru/'],
                     'rules':[rule('a[href*="/visit/gallery/"]:has(h3)','h3',['p.ba-inline-flex'],category='Выставка',force_period=True)]},
 'garagemca.org':{'adapter':'cards','seeds':['https://garagemca.org/calendar'],
                     'rules':[rule('a[href*="/event/"]','.underline-text',['[aria-label^="С "]'],aria_date='[aria-label^="С "]')]},
}

def main():
    museums=json.loads((ROOT/'data/museums.json').read_text(encoding='utf8'))
    cache={r['key']:r for r in map(json.loads,(ROOT/'data/site-results.jsonl').read_text(encoding='utf8').splitlines())}
    path=ROOT/'data/event-profiles.json'
    existing=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    profiles={}
    for m in museums:
        for site in m['sites']:
            domain=urlparse(site).hostname.removeprefix('www.')
            if domain in profiles:continue
            r=cache.get(domain,{})
            roots=[]
            for u in r.get('agenda',[]):
                u=urldefrag(u)[0];p=urlparse(u)
                if p.hostname and p.hostname.removeprefix('www.')==domain and not re.search(r'archive|collection|kollek|news|policy|ticket|support_us',u,re.I):
                    if u not in roots:roots.append(u)
            # Prefer the list/calendar before individual event pages; keep one detail as a fallback.
            roots.sort(key=lambda u:(not bool(re.search(r'/(events|calendar|afisha|poster|playbill|shows)/?(?:\?|$)',u)),len(urlparse(u).path)))
            profiles[domain]={'domain':domain,'name':m['name'],'adapter':'generic','seeds':roots[:2]+[site],
                              'max_pages':4,'max_details':6,'enabled':True,'refresh_hours':12}
            profiles[domain].update(existing.get(domain,{}))
            profiles[domain].update(CUSTOM.get(domain,{}))
            if domain in CUSTOM:profiles[domain]['max_pages']=8;profiles[domain]['max_details']=0
    path.write_text(json.dumps(profiles,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'{len(profiles)} source profiles; {len(set(CUSTOM)&set(profiles))} individual adapters')
if __name__=='__main__':main()
