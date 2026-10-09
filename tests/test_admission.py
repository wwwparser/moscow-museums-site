import unittest
from src.services.admission_collector import text_page,pricing_links
from src.services.admission_extract import validate

class AdmissionTests(unittest.TestCase):
    def test_table_category_context_and_links(self):
        html='<nav>Бесплатно</nav><main><table><tr><td>Взрослые</td><td>1 200 руб.</td></tr></table><a href="/visitors/prices">Стоимость билетов</a><a href="https://shop.example/prices">Цены сувениров</a></main>'
        text=text_page(html)
        self.assertIn('Взрослые',text)
        self.assertNotIn('Бесплатно',text)
        self.assertEqual(pricing_links(html,'https://museum.example/','museum.example'),['https://museum.example/visitors/prices'])

    def test_unconfirmed_price_and_free_entry_are_rejected(self):
        docs=[{'source':'https://museum.example/prices','text':'Взрослые 1 200 руб. Дети до 7 лет бесплатно.'}]
        good={'category':'Взрослые','price_text':'1 200 руб.','amount_rub':1200,'source':docs[0]['source'],'quote':'Взрослые 1 200 руб.'}
        result=validate({'tickets':[good,dict(good,amount_rub=500),dict(good,amount_rub=0)],'free_rules':[{'source':docs[0]['source'],'quote':'Дети до 7 лет бесплатно.','category':'Дети до 7 лет','when':'бесплатно','rule_type':'benefit'}]},docs)
        self.assertEqual(len(result['tickets']),1)
        self.assertEqual(len(result['free_rules']),1)
        self.assertEqual(len(result['rejected']),2)

    def test_source_evidence_cannot_be_fabricated(self):
        docs=[{'source':'https://museum.example/prices','text':'Взрослые 500 руб.'}]
        obj={'tickets':[{'category':'Взрослые','price_text':'100 руб.','amount_rub':100,'source':docs[0]['source'],'quote':'Взрослые 100 руб.'}]}
        self.assertEqual(validate(obj,docs)['tickets'],[])

    def test_free_list_heading_does_not_extend_to_paid_categories(self):
        source='https://museum.example/rules'
        text='Право бесплатного посещения предоставляется: Дети до 6 лет включительно. Право льготного посещения: Студенты и пенсионеры.'
        rules=[{'source':source,'quote':quote,'category':quote,'rule_type':'benefit'} for quote in ['Дети до 6 лет включительно.','Студенты и пенсионеры.']]
        result=validate({'free_rules':rules},[{'source':source,'text':text}])
        self.assertEqual(len(result['free_rules']),1)
        self.assertEqual(result['free_rules'][0]['category'],'Дети до 6 лет включительно.')

if __name__=='__main__':unittest.main()
