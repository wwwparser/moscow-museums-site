"""Parse a date field, never a whole news/article body. Preserve ambiguous periods."""
from datetime import datetime, date, timedelta
import re

MONTHS = {'январ':1,'феврал':2,'март':3,'апрел':4,'мая':5,'май':5,'июн':6,
          'июл':7,'август':8,'сентябр':9,'октябр':10,'ноябр':11,'декабр':12,
          'янв':1,'фев':2,'апр':4,'сен':9,'сент':9,'окт':10,'ноя':11,'дек':12}
MONTH = r'(?:январ[ья]|феврал[ья]|марта?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|августа?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]|янв\.?|фев\.?|апр\.?|июн\.?|июл\.?|сен\.?|сент\.?|окт\.?|ноя\.?|дек\.?)'

def month_number(text):
    return next((v for k,v in MONTHS.items() if text.startswith(k)), None)

def parse_date_field(text, reference=None, allow_inferred_year=False, date_list=False):
    reference = reference or date.today()
    text = re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip().lower()
    if not text:
        return []
    explicit_years = re.findall(r'\b(20\d{2})\b', text)
    default_year = int(explicit_years[-1]) if explicit_years else reference.year if allow_inferred_year else None
    found=[]
    iso = list(re.finditer(r'\b(20\d{2})-(\d{2})-(\d{2})(?:[t ](\d{2}):(\d{2})(?::\d{2})?(?:z|[+-]\d{2}:\d{2})?)?', text))
    inferred=False
    if iso:
        for m in iso:
            try:
                dt=datetime(int(m[1]),int(m[2]),int(m[3]))
                if m[4]:dt=dt.replace(hour=int(m[4]),minute=int(m[5]))
                found.append((dt,bool(m[4]),m.start(),m.end()))
            except ValueError:pass
    else:
        numeric=list(re.finditer(r'(?<![\d.])(\d{1,2})\.(\d{1,2})(?:\.(20\d{2}))?(?![\d.])',text))
        for m in numeric:
            year=int(m[3]) if m[3] else default_year
            if year is None:continue
            try:found.append((datetime(year,int(m[2]),int(m[1])),False,m.start(),m.end()));inferred |= not bool(m[3] or explicit_years)
            except ValueError:pass
        if not numeric:
            pattern=rf'(?<!\d)(\d{{1,2}}(?:\s*(?:,|[-–—])\s*\d{{1,2}})*)\s*({MONTH})(?:\s*,?\s*(20\d{{2}}))?'
            for m in re.finditer(pattern,text):
                year=int(m[3]) if m[3] else default_year
                if year is None:continue
                # December-to-January plans without a year need a marked rollover.
                month=month_number(m[2]); year += int(not explicit_years and reference.month>=10 and month<=2)
                groups=m[1].split(',')
                days=[]
                for group in groups:
                    numbers=[int(x) for x in re.findall(r'\d+',group)]
                    if date_list and len(numbers)==2:
                        days.extend(range(numbers[0],numbers[1]+1))
                    else:days.extend(numbers)
                for day in days:
                    try:found.append((datetime(year,month,day),False,m.start(),m.end()));inferred |= not bool(m[3] or explicit_years)
                    except ValueError:pass
    if not found:return []
    found=list(dict.fromkeys(found))
    if not iso:
        # Treat hh:mm as time only; dot-separated opening hours are not dates.
        times=re.findall(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)',text)
        if times and len(found)==1:
            dt,_,a,b=found[0]
            found[0]=(dt.replace(hour=int(times[0][0]),minute=int(times[0][1])),True,a,b)
            if len(times)>1 and re.search(r'\d\d:\d\d\s*[-–—]\s*\d\d:\d\d',text):
                end=dt.replace(hour=int(times[1][0]),minute=int(times[1][1]))
                if end>=found[0][0]:found.append((end,True,a,b))
    is_period = len(found)==2 and not date_list and bool(re.search(r'[-–—]|\bпо\b|\bдо\b', text))
    if is_period and found[-1][0]<found[0][0]:
        if explicit_years:return []
        last=found[-1];found[-1]=(last[0].replace(year=last[0].year+1),last[1],last[2],last[3])
    def serial(item):
        return item[0].isoformat(timespec='minutes')+'+03:00' if item[1] else item[0].date().isoformat()
    def row(first,last=None):
        period=last is not None and first[0].date()!=last[0].date()
        return {'start':serial(first),'end':serial(last) if last else '',
                'date_precision':'time' if first[1] else 'day','year_inferred':inferred,
                'schedule_type':'period' if period else 'session' if first[1] else 'day', 'date_text':text}
    if is_period:return [row(found[0],found[-1])]
    return [row(x) for x in found]
