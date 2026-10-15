import json
from pathlib import Path
import tempfile
import unittest
from evaluation import audit, score

class AccountingTests(unittest.TestCase):
    def test_counters_not_added_twice_and_state_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            usage={'input_tokens':100,'cached_input_tokens':20,'output_tokens':30,'reasoning_output_tokens':10}
            (path/'provider-1.jsonl').write_text(json.dumps({'type':'thread.started','thread_id':'a'})+'\n'+json.dumps({'type':'turn.completed','usage':usage}),encoding='utf-8')
            (path/'state.json').write_text(json.dumps({'usage':[usage]}),encoding='utf-8')
            result=audit(path)
            self.assertEqual(result['totals']['input_tokens'],100)
            self.assertEqual(result['totals']['output_tokens'],30)
            self.assertTrue(result['state_totals_match'])
            self.assertEqual(result['calls'],1)

    def test_ambiguous_completion_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'provider-1.jsonl').write_text('{}\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'COMPLETION_COUNT'): audit(path)

    def test_coverage_is_not_claimed_semantic_proof(self):
        result=score({'claims':[]},{})
        self.assertEqual(result['covered_topics'],0)
        self.assertFalse(result['structural_and_quote_check']['passed'])
        self.assertEqual(result['semantic_correctness'],'REQUIRES_SEPARATE_REVIEW')

if __name__=='__main__':unittest.main()
