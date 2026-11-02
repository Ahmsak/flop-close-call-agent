"""Synthetic captures; no signature, finality or real receipt is fabricated."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_inference_durable as helpers
from durable import Durable
from ops import strict_json
from flop_evidence import FORMAT, OfflineEvidenceReader, classify, expected_identity


class EvidenceTests(unittest.TestCase):
    setUp=helpers.InferenceTests.setUp
    save=helpers.InferenceTests.save
    prepare=helpers.InferenceTests.prepare
    reopen=helpers.InferenceTests.reopen

    def operation(self,slot='one'):
        genesis='0x'+'a'*64
        self.p['automation_inference']['genesis']=genesis
        key=self.prepare(slot,genesis=genesis)
        self.q.authorize_inference(key,self.policy);self.q.submit_inference_intent(key,self.policy)
        return key

    def capture(self,key):
        return {'format':FORMAT,'identity':expected_identity(self.q.inference(key)),
                'http_status':200,'gateway_request_id':'synthetic-request-1',
                'response':json.loads((Path(__file__).parent/'fixtures/flop_completion.json').read_text())}

    def observe(self,key,capture):
        result=self.q.reconcile_evidence(key,OfflineEvidenceReader(capture))
        self.assertEqual(self.q.inference(key)['state'],'UNKNOWN')
        self.assertEqual(self.q.inference(key)['held'],'32')
        self.assertFalse(result['can_release_reservation'])
        return result

    def test_valid_gateway_acceptance_and_completion(self):
        key=self.operation();capture=self.capture(key);accepted={**capture,'http_status':202,'response':None}
        self.assertEqual(self.observe(key,accepted)['level'],'GATEWAY_ACCEPTED')
        result=self.observe(key,capture)
        self.assertEqual(result['level'],'INFERENCE_COMPLETED')
        self.assertEqual(result['settlement'],'UNKNOWN')
        self.assertNotIn('cost_flop',json.dumps(result))

    def test_wrong_network_genesis_operation_fingerprint_model_and_keys(self):
        key=self.operation();original=self.capture(key)
        for field in original['identity']:
            capture=copy.deepcopy(original);capture['identity'][field]='other'
            self.assertEqual(self.observe(key,capture)['status'],'REJECTED_EVIDENCE')

    def test_unpinned_legacy_genesis_is_unverifiable(self):
        key=self.prepare();self.q.authorize_inference(key,self.policy);self.q.submit_inference_intent(key,self.policy)
        self.assertEqual(self.observe(key,self.capture(key))['reason'],'GENESIS_NOT_PINNED')

    def test_genesis_policy_and_duplicate_identity(self):
        key=self.prepare(genesis='0x'+'a'*64)
        with self.assertRaises(PermissionError):self.q.authorize_inference(key,self.policy)
        with self.assertRaises(ValueError):self.prepare(genesis='0x'+'b'*64)

    def claim(self):
        return {'unit':'synthetic-raw','inference_units':7,'fee_units':1,'finalized':True,'escrow_closed':True}

    def test_forged_receipt_and_claimed_finality_never_release(self):
        key=self.operation();capture=self.capture(key)
        capture['response']['x_flop_receipt']={'verified':True,'signature':'forged','finalized':True}
        capture['settlement']=self.claim()
        capture['refs']={'receipt_id':'synthetic-receipt','channel_id':'0x'+'c'*64,'transaction_hash':'0x'+'d'*64}
        result=self.observe(key,capture)
        self.assertEqual(result['settlement'],'UNVERIFIABLE')
        self.assertNotEqual(result['level'],'SETTLEMENT_FINALIZED')
        self.assertEqual(result['cryptographic_verification'],'UNSUPPORTED')

    def test_incomplete_finality_and_unknown_receipt_format(self):
        key=self.operation();capture=self.capture(key)
        capture['settlement']={**self.claim(),'finalized':False,'escrow_closed':False}
        self.assertEqual(self.observe(key,capture)['settlement'],'UNVERIFIABLE')
        capture['format']='future-schema'
        self.assertEqual(self.observe(key,capture)['status'],'UNSUPPORTED')

    def test_exact_cost_units_and_refs(self):
        key=self.operation()
        for field,value in [('unit','USD'),('inference_units',1.0),('fee_units',True),('fee_units',-1),('finalized','true')]:
            capture=self.capture(key);capture['settlement']={**self.claim(),field:value}
            self.assertEqual(self.observe(key,capture)['status'],'REJECTED_EVIDENCE')
        capture=self.capture(key);capture['refs']={'transaction_hash':'not-a-hash'}
        self.assertEqual(self.observe(key,capture)['status'],'REJECTED_EVIDENCE')

    def test_replay_same_operation_idempotent_after_restart(self):
        key=self.operation();capture=self.capture(key)
        self.observe(key,capture);before=self.s.diagnose();self.reopen()
        result=self.observe(key,capture)
        self.assertEqual(result['replay'],'DUPLICATE_SAME_OPERATION')
        self.assertEqual(before,self.s.diagnose())

    def test_replay_foreign_operation_rejected_even_rebound_capture(self):
        key=self.operation();capture=self.capture(key);self.observe(key,capture)
        other=self.operation('two');capture['identity']=expected_identity(self.q.inference(other))
        self.assertEqual(self.observe(other,capture)['reason'],'REPLAY_OR_CONFLICT')

    def test_receipt_reuse_different_gateway_and_completion(self):
        key=self.operation();capture=self.capture(key);capture['refs']={'receipt_id':'shared-fixture'}
        self.observe(key,capture)
        other=self.operation('two');capture=self.capture(other);capture['gateway_request_id']='other-request'
        capture['response']['id']='other-completion';capture['refs']={'receipt_id':'shared-fixture'}
        self.assertEqual(self.observe(other,capture)['status'],'REJECTED_EVIDENCE')

    def test_conflicting_response_and_settlement_preserve_original(self):
        key=self.operation();capture=self.capture(key);capture['settlement']=self.claim()
        first=self.observe(key,capture)
        for change in ['response','settlement']:
            other=copy.deepcopy(capture)
            if change=='response':other['response']['choices'][0]['message']['content']='changed'
            else:other['settlement']['fee_units']=2
            self.assertEqual(self.observe(key,other)['status'],'REJECTED_EVIDENCE')
        stored=self.q.db.execute('SELECT value FROM metadata WHERE key=?',('inference_evidence:'+key,)).fetchone()[0]
        self.assertEqual(strict_json(stored),first)

    def test_reference_cannot_disappear_from_saved_evidence(self):
        key=self.operation();capture=self.capture(key)
        capture['refs']={'receipt_id':'synthetic-bound-receipt'}
        self.observe(key,capture);del capture['refs']
        self.assertEqual(self.observe(key,capture)['status'],'REJECTED_EVIDENCE')

    def test_temporary_read_failure_and_missing_response(self):
        key=self.operation()
        with patch.object(OfflineEvidenceReader,'lookup',side_effect=TimeoutError('private')):
            result=self.observe(key,None)
            self.assertEqual(result['status'],'UNKNOWN');self.assertNotIn('private',json.dumps(result))
        self.assertEqual(self.observe(key,None)['status'],'UNKNOWN')

    def test_crash_rolls_back_claims_and_reconciliation_restarts(self):
        key=self.operation();capture=self.capture(key);self.q.recover_inference(key)
        with patch.object(self.s,'event',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.q.reconcile_evidence(key,OfflineEvidenceReader(capture))
        self.assertEqual(self.q.db.execute("SELECT count(*) FROM metadata WHERE key LIKE 'inference_evidence%'").fetchone()[0],0)
        self.reopen();self.assertEqual(self.observe(key,capture)['level'],'INFERENCE_COMPLETED')

    def test_no_migration_or_terminal_backdoor(self):
        key=self.operation();capture=self.capture(key);before=self.s.diagnose()
        Durable(self.s);self.assertEqual(before,self.s.diagnose())
        reader=OfflineEvidenceReader(capture)
        with self.assertRaises(PermissionError):self.q.reconcile_inference(key,reader)
        reader.environment='live'
        with self.assertRaises(PermissionError):self.q.reconcile_evidence(key,reader)

    def test_schema_errors_unknown_stream_and_numeric_types(self):
        key=self.operation()
        for modify in [lambda c:c['response'].update(created=True),
                       lambda c:c['response']['usage'].update(total_tokens=9),
                       lambda c:c['response']['usage'].update(cost_flop=float('nan')),
                       lambda c:c['response'].update(model='wrong'),
                       lambda c:c.update(http_status=True)]:
            capture=self.capture(key);modify(capture)
            self.assertEqual(self.observe(key,capture)['status'],'REJECTED_EVIDENCE')
        capture=self.capture(key);capture['response']['object']='chat.completion.chunk'
        self.assertEqual(self.observe(key,capture)['status'],'UNSUPPORTED')
        self.assertEqual(self.observe(key,'{"format":1,"format":2}')['status'],'REJECTED_EVIDENCE')
