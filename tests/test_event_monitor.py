from datetime import date
import json
import unittest
from unittest.mock import patch
from src.services.event_dates import parse_date_field
from src.services.event_adapters import generic,parse_page,tretyakov
from src.services.event_monitor import normalize_events,monitor,event_identity

REF=date(2026,10,9)
class EventMonitorTests(unittest.TestCase):
    def test_explicit_time_and_date_range(self):
        e=parse_date_field('17 октября 2026 года в 19:00',REF)[0]
        self.assertEqual(e['start'],'2026-10-17T19:00+03:00')
        self.assertFalse(e['year_inferred'])
        e=parse_date_field('18.10.2026–01.11.2026, 12:15',REF)[0]
        self.assertEqual(e['schedule_type'],'period')
        self.assertEqual(e['end'],'2026-11-01')
        self.assertEqual(e['date_precision'],'day')

    def test_list_days_and_ambiguous_year(self):
        self.assertEqual(parse_date_field('13 октября в 19:00',REF),[])
        inferred=parse_date_field('13 октября в 19:00',REF,True)[0]
        self.assertTrue(inferred['year_inferred'])
        rows=parse_date_field('10, 11, 13, 29–31 октября',REF,True,True)
        self.assertEqual([r['start'] for r in rows],['2026-10-10','2026-10-11','2026-10-13','2026-10-29','2026-10-30','2026-10-31'])

    def test_calendar_does_not_use_article_publication_date(self):
        html='<article><a href="/news/concert">Новая программа</a><time datetime="2026-10-12">12 октября</time></article>'
        self.assertEqual(generic(html,'https://museum.example/',REF),[])
        html='<article><a href="/events/concert">Вечер в музее</a><time datetime="2026-10-12T19:00">12 октября</time></article>'
        self.assertEqual(len(generic(html,'https://museum.example/',REF)),1)

    def test_individual_markup_uses_correct_time(self):
        html='<a class="sched__row" href="/events/one"><h3 class="sched__title">Лекция</h3><time datetime="2026-10-13T19:30"></time></a>'
        profile={'adapter':'cards','rules':[{'card':'a.sched__row','title':'.sched__title','date':['time']}]}
        rows=parse_page(html,'https://mamm.art/events/',profile,REF)
        self.assertEqual(rows[0]['start'],'2026-10-13T19:30+03:00')
        self.assertEqual(rows[0]['url'],'https://mamm.art/events/one')

    def test_day_list_keeps_holidays_out_of_recurrence(self):
        rows=[{'title':'Экскурсия','url':'https://m.example/tour','source':'https://m.example/calendar','date_precision':'day','start':d,'end':''} for d in ['2026-10-10','2026-10-11','2026-10-13']]
        rows=normalize_events(rows,REF,30,'m.example')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['occurrence_dates'],['2026-10-10','2026-10-11','2026-10-13'])
        self.assertNotIn('2026-10-12',rows[0]['occurrence_dates'])

    def test_exhibition_closing_date_is_not_a_session(self):
        html='<a data-date="1791493200" href="/events/show"><h3>Выставка</h3><p>до 22 ноября 2026</p></a>'
        profile={'rules':[{'card':'a','title':'h3','date':['p'],'start_unix_attr':'data-date'}]}
        e=parse_page(html,'https://museum.example/',profile,REF)[0]
        self.assertEqual(e['schedule_type'],'period')
        self.assertEqual(e['end'],'2026-11-22')
        self.assertLess(e['start'],e['end'])
        profile['rules'][0].pop('start_unix_attr')
        self.assertEqual(parse_page(html,'https://museum.example/',profile,REF),[])

    def test_two_exhibition_dates_are_a_period(self):
        html='<a href="/events/show"><h3>Выставка</h3><p>1 октября 2026 22 ноября 2026</p></a>'
        profile={'rules':[{'card':'a','title':'h3','date':['p'],'force_period':True}]}
        e=parse_page(html,'https://museum.example/',profile,REF)[0]
        self.assertEqual((e['start'],e['end']),('2026-10-01','2026-11-22'))
        self.assertEqual(e['schedule_type'],'period')

    def test_failure_keeps_last_good_data_without_cancellation(self):
        future=date.today().replace(day=28).isoformat()
        e={'title':'Лекция','url':'https://m.example/events/one','source':'https://m.example/events','start':future,'end':'','date_precision':'day'}
        e['monitor_id']=event_identity(e)
        profile={'domain':'m.example','name':'Музей','adapter':'generic','seeds':['https://m.example/'],'max_pages':1}
        with patch('src.services.event_monitor.fetch',side_effect=RuntimeError('timeout')):
            result=monitor(profile,30,{'events':[e]})
        self.assertTrue(result['stale'])
        self.assertEqual(result['changes']['removed'],0)
        self.assertEqual(len(result['events']),1)

    def test_api_adapter_uses_api_dates_and_venue(self):
        obj={'data':{'items':[{'name':'Лекция','url':'/events/lecture','startDate':'20 октября 2026 19:00','place':{'name':'Новая Третьяковка'}}]}}
        rows,urls=tretyakov(lambda url,**kw:(json.dumps(obj),url),REF,30)
        self.assertEqual(rows[0]['start'],'2026-10-20T19:00+03:00')
        self.assertEqual(rows[0]['venue'],'Новая Третьяковка')

if __name__=='__main__':unittest.main()
