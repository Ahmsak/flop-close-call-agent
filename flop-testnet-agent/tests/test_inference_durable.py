"""Provisional offline inference accounting, not FLOP API fixtures."""
import tempfile
import threading
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from durable import Durable, Policy
from ops import Store, canonical, digest


class Reader:
    environment='sandbox'
    read_only=True
    def __init__(self, evidence, verified=True): self.evidence,self.verified=evidence,verified
    def lookup(self, identity): return self.evidence
    def verify(self, identity, evidence): return self.verified


class InferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'db.sqlite';self.now=100000
        self.s=Store(self.path,create=True);self.addCleanup(lambda:self.s.close())
        self.q=Durable(self.s,clock=lambda:self.now)
        self.p={'execution':'EXECUTION_DISABLED','owner_did':'synthetic','real_money_budget':'0',
                'automation_inference':{'environment':'sandbox','network':'devnet', 'unit':'synthetic-raw',
                'operation_allowlist':[],'inference_cap':10,'escrow_cap':20,'fee_cap':2,
                'daily_cap':64,'session_cap':64}}
        self.policy=Policy(self.root/'policy.json');self.save()
        self.task=self.q.enqueue({'goal':'offline','input':{},'criterion':'fixture','artifact':'none',
                                  'stop':'one','max_attempts':1,'max_units':1},self.policy)

    def save(self): self.policy.path.write_text(canonical(self.p))

    def prepare(self, slot='one', **changes):
        args=dict(session='session',network='devnet',model='fixture/model',request_fingerprint=digest({'input':'fixture'}),
                  unit='synthetic-raw',price_at=99999,price_expires=100100,inference_cap=10,escrow_cap=20,fee_cap=2)
        args.update(changes)
        key=self.q.prepare_inference(self.task,slot,**args)
        if key not in self.p['automation_inference']['operation_allowlist']:
            self.p['automation_inference']['operation_allowlist'].append(key);self.save()
        return key

    def submitted(self):
        key=self.prepare();self.q.authorize_inference(key,self.policy)
        self.q.submit_inference_intent(key,self.policy);return key

    def reopen(self):
        self.s.close();self.s=Store(self.path);self.q=Durable(self.s,clock=lambda:self.now)

    def evidence(self,key,**changes):
        row=self.q.inference(key)
        data={'identity':{k:row[k] for k in ('id','idempotency_key','correlation_id','network','model','fingerprint')},
              'state':'CONFIRMED','finalized':True,'escrow_closed':True,'inference_units':7,'fee_units':1,
              'receipt_id':'synthetic-receipt'}
        data.update(changes);return data

    def test_duplicate_and_request_mutation(self):
        key=self.prepare();self.assertEqual(self.prepare(),key)
        with self.assertRaisesRegex(ValueError,'IDENTITY_CONFLICT'):self.prepare(request_fingerprint=digest('changed'))
        row=self.q.inference(key);self.reopen()
        self.assertEqual(row,self.q.inference(key))
        self.assertEqual(self.q.db.execute('SELECT count(*) FROM automation_inference').fetchone()[0],1)

    def test_crash_before_submission_authorized_is_recoverable(self):
        key=self.prepare();self.q.authorize_inference(key,self.policy);self.reopen()
        self.assertEqual(self.q.recover_inference(key)['state'],'AUTHORIZED')
        self.assertEqual(self.q.submit_inference_intent(key,self.policy)['state'],'SUBMITTED')
        with self.assertRaisesRegex(RuntimeError,'RESEND'):self.q.submit_inference_intent(key,self.policy)

    def test_crash_after_intent_before_wire_is_uncertain(self):
        key=self.submitted();self.reopen()
        self.assertEqual(self.q.recover_inference(key)['state'],'UNKNOWN')
        self.assertEqual(self.q.inference(key)['held'],'32')
        with self.assertRaises(RuntimeError):self.q.submit_inference_intent(key,self.policy)

    def test_lost_response_after_simulated_submission_and_restart(self):
        key=self.submitted();external_calls=[key]  # simulated effect, no HTTP
        self.reopen();self.q.recover_inference(key);self.reopen()
        self.assertEqual(self.q.inference(key)['state'],'UNKNOWN')
        with self.assertRaises(RuntimeError):self.q.submit_inference_intent(key,self.policy)
        self.assertEqual(external_calls,[key])

    def test_abrupt_process_exit_before_and_after_synthetic_wire(self):
        code='''import os,sys
from pathlib import Path
from ops import Store
from durable import Durable,Policy
s=Store(sys.argv[1]);q=Durable(s,clock=lambda:100000)
q.submit_inference_intent(sys.argv[3],Policy(sys.argv[2]))
if sys.argv[4]=='after': Path(sys.argv[5]).write_text('one synthetic effect')
os._exit(17)
'''
        for phase in ['before','after']:
            key=self.prepare(phase);self.q.authorize_inference(key,self.policy)
            effect=self.root/(phase+'.txt')
            args=[sys.executable,'-B','-c',code,str(self.path),str(self.policy.path),key,phase,str(effect)]
            first=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(first.returncode,17,first.stderr)
            self.assertEqual(effect.exists(),phase=='after')
            self.reopen();self.q.recover_inference(key)
            second=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertNotEqual(second.returncode,0)
            self.assertIn('INFERENCE_RESEND_FORBIDDEN',second.stderr)
            self.assertEqual(self.q.inference(key)['held'],'32')

    def test_unknown_no_evidence_never_releases(self):
        key=self.submitted()
        for reader in [Reader(None), Reader(self.evidence(key),False)]:
            result=self.q.reconcile_inference(key,reader)
            self.assertEqual((result['state'],result['held']),('UNKNOWN','32'))

    def test_verified_terminal_release_and_spend_retained(self):
        key=self.submitted();result=self.q.reconcile_inference(key,Reader(self.evidence(key)))
        self.assertEqual((result['state'],result['held'],result['spent']),('CONFIRMED','0','8'))
        self.reopen();before=self.s.diagnose()
        with patch.object(Reader,'lookup',side_effect=AssertionError('no second lookup')):
            self.assertEqual(self.q.reconcile_inference(key,Reader(None))['state'],'CONFIRMED')
        self.assertEqual(before,self.s.diagnose())
        self.p['automation_inference']['session_cap']=39;other=self.prepare('two')
        with self.assertRaises(PermissionError):self.q.authorize_inference(other,self.policy)

    def test_failed_is_not_free_fees_and_settlement_required(self):
        key=self.submitted()
        result=self.q.reconcile_inference(key,Reader(self.evidence(key,state='FAILED',inference_units=0,fee_units=2)))
        self.assertEqual((result['state'],result['held'],result['spent']),('FAILED','0','2'))

    def test_unverified_nonfinal_wrong_identity_and_overcharge(self):
        key=self.submitted()
        for change in [dict(finalized=False),dict(escrow_closed=False),dict(state='PENDING'),
                       dict(identity={}),dict(inference_units=11),dict(fee_units=3),dict(fee_units=1.0)]:
            result=self.q.reconcile_inference(key,Reader(self.evidence(key,**change)))
            self.assertEqual((result['state'],result['held']),('UNKNOWN','32'))

    def test_live_reader_rejected(self):
        key=self.submitted();reader=Reader(None);reader.environment='live'
        with self.assertRaises(PermissionError):self.q.reconcile_inference(key,reader)
        self.assertEqual(self.q.inference(key)['held'],'32')

    def test_verified_overcharge_blocks_new_budget_domain_reservations(self):
        key=self.submitted()
        self.q.reconcile_inference(key,Reader(self.evidence(key,inference_units=11)))
        self.reopen();other=self.prepare('two',session='another-session')
        with self.assertRaisesRegex(PermissionError,'BUDGET_RECONCILIATION'):
            self.q.authorize_inference(other,self.policy)
        self.assertEqual(self.q.inference(key)['held'],'32')

    def test_wrong_network_stale_price_and_scope(self):
        key=self.prepare(network='testnet')
        with self.assertRaises(PermissionError):self.q.authorize_inference(key,self.policy)
        for args in [dict(price_expires=100000),dict(price_at=100001,price_expires=100002)]:
            key=self.prepare('price'+str(args['price_expires']),**args)
            with self.assertRaises(PermissionError):self.q.authorize_inference(key,self.policy)
        key=self.prepare('scope');self.p['automation_inference']['environment']='live';self.save()
        with self.assertRaises(PermissionError):self.q.authorize_inference(key,self.policy)

    def test_floats_bools_strings_negative_rejected_and_large_int_exact(self):
        for value in [0.1,True,'1',-1]:
            with self.assertRaises(ValueError):self.prepare(inference_cap=value)
        large=10**30
        key=self.prepare(inference_cap=large)
        self.p['automation_inference'].update(inference_cap=large,daily_cap=large+22,session_cap=large+22);self.save()
        self.assertEqual(self.q.authorize_inference(key,self.policy)['held'],str(large+22))

    def test_insufficient_and_component_caps(self):
        key=self.prepare()
        for field,value in [('daily_cap',31),('session_cap',31),('inference_cap',9),('escrow_cap',19),('fee_cap',1)]:
            old=self.p['automation_inference'][field];self.p['automation_inference'][field]=value;self.save()
            with self.assertRaises(PermissionError):self.q.authorize_inference(key,self.policy)
            self.assertEqual(self.q.inference(key)['held'],'0')
            self.p['automation_inference'][field]=old

    def test_concurrent_reservations_atomic(self):
        keys=[self.prepare('one'),self.prepare('two')]
        self.p['automation_inference']['daily_cap']=32;self.save()
        barrier=threading.Barrier(2);results=[]
        def reserve(key):
            s=Store(self.path)
            try:
                q=Durable(s,clock=lambda:self.now);barrier.wait()
                try:q.authorize_inference(key,self.policy);results.append('OK')
                except PermissionError:results.append('BLOCKED')
            finally:s.close()
        threads=[threading.Thread(target=reserve,args=(k,)) for k in keys]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(results,['OK','BLOCKED'])

    def test_reservation_survives_day_rollover_and_session_shared(self):
        key=self.submitted();self.q.recover_inference(key)
        self.now+=86400;self.p['automation_inference']['daily_cap']=63
        other=self.prepare('tomorrow',price_at=self.now-1,price_expires=self.now+100)
        with self.assertRaises(PermissionError):self.q.authorize_inference(other,self.policy)
        self.assertEqual(self.q.inference(key)['held'],'32')

    def test_authorization_rechecked_at_intent(self):
        key=self.prepare();self.q.authorize_inference(key,self.policy)
        self.now=100101
        with self.assertRaises(PermissionError):self.q.submit_inference_intent(key,self.policy)
        self.assertEqual(self.q.inference(key)['state'],'AUTHORIZED')

    def test_event_failure_rolls_back_budget_and_terminal(self):
        key=self.prepare()
        with patch.object(self.s,'event',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.q.authorize_inference(key,self.policy)
        self.assertEqual(self.q.inference(key)['held'],'0')
        self.q.authorize_inference(key,self.policy);self.q.submit_inference_intent(key,self.policy)
        self.q.recover_inference(key)
        with patch.object(self.s,'event',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.q.reconcile_inference(key,Reader(self.evidence(key)))
        self.assertEqual(self.q.inference(key)['held'],'32')

    def test_additive_migration_old_schema_and_repeat(self):
        self.q.db.execute('DROP TABLE automation_inference');self.q.db.commit()
        before=self.s.diagnose();task=self.q.task(self.task)
        Durable(self.s);Durable(self.s)
        self.assertEqual(self.s.diagnose(),before)
        self.assertEqual(self.q.task(self.task),task)
        self.assertEqual(self.q.db.execute("SELECT value FROM metadata WHERE key='automation_schema'").fetchone()[0],'1')
