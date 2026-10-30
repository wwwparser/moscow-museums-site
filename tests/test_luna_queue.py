import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import prepare_luna_queue
from scripts.collect_admission import validate_known
from src.services.admission_evidence import evidence_fingerprint
from src.services.llm_client import ExternalLLMDisabled, choose_provider, config, extract_json


class LunaQueueTests(unittest.TestCase):
    def run_queue(self, temp, documents, results):
        root = Path(temp)
        (root / 'data').mkdir(exist_ok=True)
        (root / 'data/admission-documents.jsonl').write_text(
            ''.join(json.dumps(row) + '\n' for row in documents.values()), encoding='utf8')
        (root / 'data/admission-results.jsonl').write_text(
            ''.join(json.dumps(row) + '\n' for row in results.values()), encoding='utf8')
        with patch.object(prepare_luna_queue, 'ROOT', root):
            prepare_luna_queue.main(['--output', 'data/test-queue.json'])
        return json.loads((root / 'data/test-queue.json').read_text(encoding='utf8'))['items']

    def test_current_applied_luna_result_stays_closed_with_fetch_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); evidence = root / 'evidence.txt'; evidence.write_text('Current public admission evidence.', encoding='utf8')
            docs = {'museum.test': {'key':'museum.test','checked_at':'2026-10-30T10:00:00Z','status':'documents_found',
                'errors':[{'url':'https://museum.test/prices','error':'timeout'}], 'documents':[{'source':'https://museum.test/fees','file':str(evidence)}]}}
            results = {'museum.test': {'key':'museum.test','processor':'internal-luna','checked_at':'2026-10-30T10:00:00Z',
                'luna_checked_at':'2026-10-30T10:00:00Z','needs_luna_review':False}}
            self.assertEqual([], self.run_queue(temp, docs, results))

    def test_unavailable_source_without_documents_is_not_queued(self):
        with tempfile.TemporaryDirectory() as temp:
            docs = {'museum.test': {'key':'museum.test','checked_at':'2026-10-30T10:00:00Z','status':'unavailable',
                'errors':[{'url':'https://museum.test','error':'timeout'}], 'documents':[]}}
            self.assertEqual([], self.run_queue(temp, docs, {}))

    def test_new_document_after_review_is_queued(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); evidence = root / 'evidence.txt'; evidence.write_text('Changed admission evidence.', encoding='utf8')
            docs = {'museum.test': {'key':'museum.test','checked_at':'2026-10-30T11:00:00Z','status':'documents_found',
                'errors':[], 'documents':[{'source':'https://museum.test/fees','file':str(evidence)}]}}
            results = {'museum.test': {'key':'museum.test','processor':'internal-luna','checked_at':'2026-10-30T10:00:00Z',
                'luna_checked_at':'2026-10-30T10:00:00Z','needs_luna_review':False}}
            items = self.run_queue(temp, docs, results)
            self.assertEqual(['museum.test'], [item['key'] for item in items])

    def test_new_checked_at_with_identical_evidence_is_not_queued(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); evidence = root / 'evidence.txt'; evidence.write_text('Same full admission text.\nSecond line.', encoding='utf8')
            source = 'https://museum.test/fees'
            digest = evidence_fingerprint([{'source':source,'text':evidence.read_text(encoding='utf8')}])
            docs = {'museum.test': {'key':'museum.test','checked_at':'2026-10-31T10:00:00Z','status':'documents_found',
                'errors':[], 'documents':[{'source':source,'file':str(evidence)}]}}
            results = {'museum.test': {'key':'museum.test','processor':'internal-luna','checked_at':'2026-10-30T10:00:00Z',
                'luna_checked_at':'2026-10-30T10:00:00Z','evidence_hash':digest,'needs_luna_review':False}}
            self.assertEqual([], self.run_queue(temp, docs, results))

    def test_changed_full_text_is_queued_even_with_same_checked_at(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); evidence = root / 'evidence.txt'; evidence.write_text('Updated price: 750 rubles.', encoding='utf8')
            source = 'https://museum.test/fees'
            digest = evidence_fingerprint([{'source':source,'text':'Old price: 500 rubles.'}])
            docs = {'museum.test': {'key':'museum.test','checked_at':'2026-10-30T10:00:00Z','status':'documents_found',
                'errors':[], 'documents':[{'source':source,'file':str(evidence)}]}}
            results = {'museum.test': {'key':'museum.test','processor':'internal-luna','checked_at':'2026-10-30T10:00:00Z',
                'luna_checked_at':'2026-10-30T10:00:00Z','evidence_hash':digest,'needs_luna_review':False}}
            items = self.run_queue(temp, docs, results)
            self.assertEqual(['museum.test'], [item['key'] for item in items])

    def test_external_llm_guards_fail_before_any_socket_call(self):
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network attempted')) as connect:
            for call in (choose_provider, lambda: config('deepseek'), lambda: extract_json('prompt')):
                with self.assertRaises(ExternalLLMDisabled):
                    call()
            connect.assert_not_called()

    def test_full_refresh_failure_preserves_last_success_as_stale(self):
        previous = {'key':'museum.test','checked_at':'2026-10-20T10:00:00Z',
            'last_success_at':'2026-10-15T10:00:00Z','tickets':[{'category':'adult'}], 'free_rules':[]}
        current = {'key':'museum.test','name':'Museum','checked_at':'2026-10-30T10:00:00Z',
            'pages':[],'links':[],'errors':[{'url':'https://museum.test','error':'timeout'}],
            'documents':[],'status':'unavailable'}
        result = validate_known(current, previous)
        self.assertTrue(result['stale'])
        self.assertEqual(previous['last_success_at'], result['last_success_at'])
        self.assertEqual(current['checked_at'], result['last_attempt_at'])


if __name__ == '__main__':
    unittest.main()
