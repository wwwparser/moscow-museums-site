import json
import unittest
from unittest.mock import patch
from src.services.site_extract import extract, channel_url, http_url
from src.services.classify import classify
from src.services.telegram_client import get_posts

class ExtractionTests(unittest.TestCase):
    def test_nested_events_missing_dates_and_unsafe_links(self):
        page = '<a href="javascript:alert(1)">Афиша</a><a href="/events">Афиша</a>'
        page += '<script type="application/ld+json">' + json.dumps({'@graph':[
            {'@type':'Event','name':'Недатированное событие'},
            {'@type':'Event','name':'<b>Лекция</b>','startDate':'2026-10-10','url':'/events/one'}]}) + '</script>'
        r = extract(page, 'https://museum.example/')
        self.assertEqual(len(r['events']), 1)
        self.assertEqual(r['events'][0]['date_precision'], 'day')
        self.assertEqual(r['events'][0]['title'], 'Лекция')
        self.assertEqual(r['agenda'], ['https://museum.example/events'])
        self.assertEqual(http_url('javascript:alert(1)'), '')

    def test_telegram_links(self):
        self.assertEqual(channel_url('https://t.me/s/museum/12'), 'https://t.me/museum')
        for value in ('https://t.me/+private', 'https://t.me/share/url?x=1', 'https://evil.t.me/museum'):
            self.assertEqual(channel_url(value), '')

    def test_last_five_public_posts(self):
        html = ''.join(f'<div class="tgme_widget_message" data-post="museum/{i}"><time datetime="2026-10-09T12:00:00Z"></time><div class="tgme_widget_message_text">Пост {i}</div></div>' for i in range(8))
        with patch('src.services.telegram_client.fetch', return_value=(html, 'https://t.me/s/museum')):
            posts = get_posts('https://t.me/museum')
        self.assertEqual(len(posts), 5)
        self.assertEqual(posts[0]['id'], 'museum/3')
        self.assertEqual(posts[-1]['id'], 'museum/7')

    def test_themes_distinguish_writer_from_art(self):
        self.assertIn('Писатели и литература', classify('Мемориальная квартира Пушкина'))
        self.assertIn('Искусство и архитектура', classify('Государственный музей изобразительных искусств имени Пушкина'))
        self.assertNotIn('Писатели и литература', classify('Государственный музей изобразительных искусств имени Пушкина'))
        self.assertIn('Военная история', classify('Центральный музей Вооружённых Сил'))
        self.assertIn('Природа и естествознание', classify('Государственный Дарвиновский музей'))
        self.assertEqual(classify('Музей 123'), ['Другие / требуют уточнения'])

if __name__ == '__main__':
    unittest.main()
