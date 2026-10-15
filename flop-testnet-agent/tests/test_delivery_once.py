import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from durable import Durable,Policy
from ops import Store,canonical
from telegram_bridge import claim_wire


class OneShotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'state.sqlite',create=True);self.addCleanup(self.store.close)
        self.q=Durable(self.store,clock=lambda:100)
        p=self.root/'config.json';p.write_text(canonical({'execution':'EXECUTION_DISABLED','real_money_budget':'0','owner_did':'fixture'}))
        self.policy=Policy(p);self.artifact=self.root/'result.html';self.artifact.write_text('test document')
        self.task=self.q.enqueue({'goal':'fixture','input':{},'criterion':'checked','artifact':str(self.artifact),'stop':'one','max_attempts':1,'max_units':1},self.policy)
        fence=self.q.claim(self.task,'test');self.nid=self.q.complete(self.task,'test',fence,{'TASK_OUTPUT_VALID':True},self.artifact)
        self.grant={'status':'OPEN','notification_id':self.nid,'task_id':self.task,'attempts':1,'expires':200,
                    'chat_id':'123','username':'fixture','artifact':str(self.artifact.resolve()),'sha256':hashlib.sha256(self.artifact.read_bytes()).hexdigest()}

    def adapter(self,response):
        parent=self
        class Adapter:
            environment='telegram';chat_id='123';username='fixture';calls=0
            def send(self,nid,destination,payload):
                self.calls+=1
                assert parent.q.db.execute('SELECT state FROM automation_outbox WHERE id=?',(nid,)).fetchone()[0]=='SENDING'
                claim_wire(parent.root/'state.sqlite',payload['delivery_grant'])
                with parent.assertRaises(Exception):claim_wire(parent.root/'state.sqlite',payload['delivery_grant'])
                if response is None:raise TimeoutError('reply lost')
                return response
        return Adapter()

    def test_accepted_and_reopen_no_resend(self):
        a=self.adapter({'accepted':True,'service_id':'fixture-1','requests':1})
        self.assertEqual(self.q.deliver(self.nid,a,self.policy,grant=self.grant)['state'],'SERVICE_ACCEPTED')
        reopened=Store(self.root/'state.sqlite')
        try:self.assertEqual(Durable(reopened).deliver(self.nid,a,self.policy,grant=self.grant)['state'],'SERVICE_ACCEPTED')
        finally:reopened.close()
        self.assertEqual(a.calls,1)

    def test_unknown_never_retried(self):
        a=self.adapter(None)
        self.assertEqual(self.q.deliver(self.nid,a,self.policy,grant=self.grant)['state'],'UNKNOWN')
        self.q.deliver(self.nid,a,self.policy,grant=self.grant)
        self.assertEqual(a.calls,1)

    def test_completed_task_block_notice_superseded_without_touching_others(self):
        spec={'goal':'blocked then complete','input':{},'criterion':'checked','artifact':str(self.artifact),'stop':'one','max_attempts':1,'max_units':1}
        key=self.q.enqueue(spec,self.policy)
        old=self.q.block(key,'MODEL_DISABLED')
        p=self.policy.read();p.update(automation_task_allowlist=[key],automation_sandbox_delivery=True)
        self.policy.path.write_text(canonical(p))
        self.q.resume_blocked(key,self.policy)
        fence=self.q.claim(key,'test')
        completed=self.q.complete(key,'test',fence,{'TASK_OUTPUT_VALID':True},self.artifact)
        other=self.q.enqueue({**spec,'goal':'another task'},self.policy)
        other_notice=self.q.block(other,'MODEL_DISABLED')
        def notice(nid):return dict(self.q.db.execute('SELECT * FROM automation_outbox WHERE id=?',(nid,)).fetchone())
        protected={nid:notice(nid) for nid in (completed,other_notice,self.nid)}
        old_before=notice(old)
        class Forbidden:
            environment='sandbox'
            def send(self,*args):raise AssertionError('no stale notification may be sent')
        result=self.q.deliver(old,Forbidden(),self.policy)
        self.assertEqual(result,{**old_before,'state':'SUPERSEDED'})
        for nid,row in protected.items():self.assertEqual(notice(nid),row)
        reopened=Store(self.root/'state.sqlite')
        try:
            sender=Forbidden();sender.environment='telegram'
            self.assertEqual(Durable(reopened).deliver(old,sender,self.policy)['state'],'SUPERSEDED')
        finally:reopened.close()
        self.assertEqual(self.q.db.execute("SELECT COUNT(*) FROM events WHERE kind='notification_superseded'").fetchone()[0],1)

    def test_rejection_and_local_block_are_distinct(self):
        a=self.adapter({'rejected':True,'requests':1})
        self.assertEqual(self.q.deliver(self.nid,a,self.policy,grant=self.grant)['state'],'FAILED')

    def test_scope_and_hash_mismatch_never_invoke_adapter(self):
        a=self.adapter(None)
        for key,value in [('notification_id','wrong'),('chat_id','456'),('sha256','wrong'),('attempts',2),('expires',99)]:
            with self.assertRaises(PermissionError):self.q.deliver(self.nid,a,self.policy,grant={**self.grant,key:value})
        self.assertEqual(a.calls,0)
        self.assertEqual(self.q.db.execute('SELECT attempts FROM automation_outbox WHERE id=?',(self.nid,)).fetchone()[0],0)

    def test_local_block_requires_new_explicit_grant_and_no_wire_marker(self):
        class Local:
            environment='telegram';chat_id='123';username='fixture'
            def send(self,*args):return {'status':'NOT_SENT','requests':0}
        self.assertEqual(self.q.deliver(self.nid,Local(),self.policy,grant=self.grant)['state'],'NOT_SENT')
        a=self.adapter({'accepted':True,'service_id':'fixture-2','requests':1})
        self.q.deliver(self.nid,a,self.policy,grant=self.grant)
        self.assertEqual(a.calls,0)
        updated={**self.grant,'retry_proven_not_sent':True,'outbox_attempt':2}
        result=self.q.deliver(self.nid,a,self.policy,grant=updated)
        self.assertEqual(result['state'],'SERVICE_ACCEPTED')
        self.assertEqual(result['attempts'],2)
        self.assertEqual(a.calls,1)
