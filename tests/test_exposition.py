import unittest
from scripts.apply_expositions import validate_record,freshness
from src.services.exposition import extract_page

class ExpositionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.url='https://example.org/collection'
        self.evidence={self.url:'The collection includes original printing presses. The memorial room preserves the writer’s desk.'}
        self.museums={'one':{'sites':['https://example.org/']},'other':{'sites':['https://another.org/']}}
        self.row={'key':'example.org'}
        self.record={'museum_ids':['one'],'scope':'venue','facts':[
            {'text':'В коллекции представлены подлинные печатные станки.','quote':'The collection includes original printing presses.','source':self.url},
            {'text':'В мемориальной комнате сохранился письменный стол писателя.','quote':'The memorial room preserves the writer’s desk.','source':self.url}]}
    def test_supported_facts(self):
        ids,facts=validate_record(self.record,self.row,self.evidence,self.museums)
        self.assertEqual(ids,['one']);self.assertEqual(len(facts),2)
        self.assertNotIn('quote',facts[0])
    def test_invented_evidence_rejected(self):
        self.record['facts'][0]['quote']='The museum has a golden royal crown.'
        with self.assertRaises(ValueError):validate_record(self.record,self.row,self.evidence,self.museums)
    def test_other_museum_rejected(self):
        self.record['museum_ids']=['other']
        with self.assertRaises(ValueError):validate_record(self.record,self.row,self.evidence,self.museums)
    def test_other_source_rejected(self):
        self.record['facts'][0]['source']='https://another.org/'
        with self.assertRaises(ValueError):validate_record(self.record,self.row,self.evidence,self.museums)
    def test_organization_scope_rejected(self):
        self.record['scope']='organization'
        with self.assertRaises(ValueError):validate_record(self.record,self.row,self.evidence,self.museums)
    def test_extract_prefers_collection_and_removes_navigation(self):
        page=extract_page('<nav>Fake collection</nav><main><p>The collection preserves original historic printing presses and manuscripts.</p><a href="/collection">Collection</a><a href="/news">News</a></main>','https://example.org/')
        self.assertNotIn('Fake',page['text']);self.assertIn(self.url,page['links'])
        self.assertNotIn('https://example.org/news',page['links'])
    def test_changed_evidence_is_stale(self):
        self.assertEqual(freshness({'evidence_hash':'old'},{'evidence_hash':'new','documents':[{}]}),'stale')
    def test_later_failure_does_not_make_note_fresh(self):
        self.assertEqual(freshness({'checked_at':'2026-10-30','evidence_hash':'same'},{'checked_at':'2026-11-02','evidence_hash':'same','documents':[]}),'stale')
if __name__=='__main__':unittest.main()
