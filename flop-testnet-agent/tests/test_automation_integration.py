import json
from pathlib import Path
import tempfile
import unittest

from ops import Store,canonical
from durable import Durable,Policy
from mission import MODEL
from mission_guard import guarded_run
from source_discovery import collect
from jobs import discover
from test_mission import DOCS,Scripted
from test_source_discovery import EVENT,page,NOW

class IntegrationTests(unittest.TestCase):
    def test_budget_resume_only_unissued_step(self):
        p=self.policy.read();p['automation_daily_units']['model']=1;self.path.write_text(canonical(p))
        result=guarded_run(DOCS,self.root/'resume-budget',self.store,self.policy,Scripted)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],1)
        p['automation_daily_units']['model']=2;p['automation_task_allowlist']=[result['task_id']]
        self.path.write_text(canonical(p))
        done=guarded_run(DOCS,self.root/'resume-budget',self.store,self.policy,Scripted,resume_blocked=True)
        self.assertEqual(done['status'],'LOCAL_COMPLETE')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],2)

    def test_malformed_policy_cannot_grant_resume_or_delivery(self):
        p=self.policy.read()
        for change in ({'automation_task_allowlist':'a-task-id'},{'automation_sandbox_delivery':'false'}):
            self.path.write_text(canonical({**p,**change}))
            with self.assertRaises(PermissionError):self.policy.read()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.store=Store(self.root/'state.sqlite',create=True); self.addCleanup(self.store.close)
        self.path=self.root/'policy.json'
        self.path.write_text(canonical({'execution':'EXECUTION_DISABLED','owner_did':'fixture','real_money_budget':'0',
            'automation_model':MODEL,'automation_daily_units':{'model':2}}))
        self.policy=Policy(self.path)

    def test_existing_mission_guard_completion_and_restart_no_new_calls(self):
        result=guarded_run(DOCS,self.root/'mission',self.store,self.policy,Scripted)
        self.assertEqual(result['status'],'LOCAL_COMPLETE')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],2)
        self.assertEqual(self.store.db.execute('SELECT state FROM automation_outbox').fetchone()[0],'PENDING')
        def forbidden(p): raise AssertionError('must not call model')
        self.assertEqual(guarded_run(DOCS,self.root/'mission',self.store,self.policy,forbidden)['status'],'LOCAL_COMPLETE')

    def test_auth_failure_remains_blocked_or_unknown_not_success(self):
        def offline(p): raise RuntimeError('AUTH_FAILED')
        result=guarded_run(DOCS,self.root/'failed',self.store,self.policy,offline)
        self.assertEqual(result['status'],'BLOCKED')
        q=Durable(self.store)
        self.assertIsNone(q.health()['marks']['sources'])
        self.assertIsNone(q.health()['marks']['model'])
        self.assertEqual(self.store.db.execute('SELECT state FROM automation_actions').fetchone()[0],'UNKNOWN')
        p=self.policy.read();p['automation_task_allowlist']=[result['task_id']];self.path.write_text(canonical(p))
        def forbidden(path):raise AssertionError('unknown model response must not be retried')
        again=guarded_run(DOCS,self.root/'failed',self.store,self.policy,forbidden,resume_blocked=True)
        self.assertEqual(again['status'],'UNKNOWN')

    def test_readonly_retains_task_and_notice_across_database_reopen(self):
        def forbidden(p): raise AssertionError('model forbidden')
        result=guarded_run(DOCS,self.root/'readonly',self.store,self.policy,forbidden,allow_model=False)
        self.assertEqual(result['status'],'BLOCKED')
        reopened=Store(self.root/'state.sqlite')
        try:
            again=guarded_run(DOCS,self.root/'readonly',reopened,self.policy,forbidden,allow_model=False)
            self.assertEqual(result,again)
            self.assertEqual(reopened.db.execute('SELECT COUNT(*) FROM automation_tasks').fetchone()[0],1)
            self.assertEqual(reopened.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],0)
            self.assertEqual(reopened.db.execute('SELECT state,attempts FROM automation_outbox').fetchone()[:],('PENDING',0))
        finally: reopened.close()

    def test_budget_block_is_persisted_before_model(self):
        self.path.write_text(canonical({'execution':'EXECUTION_DISABLED','owner_did':'fixture','real_money_budget':'0'}))
        result=guarded_run(DOCS,self.root/'budget',self.store,self.policy)
        self.assertEqual(result['reason'],'MODEL_DAILY_BUDGET_NOT_AUTHORIZED')
        self.assertEqual(Durable(self.store).task(result['task_id'])['state'],'BLOCKED')
        self.assertIsNotNone(result['outbox_id'])

    def test_explicit_task_scoped_resume_then_restart(self):
        result=guarded_run(DOCS,self.root/'resume',self.store,self.policy,allow_model=False)
        denied=guarded_run(DOCS,self.root/'resume',self.store,self.policy,Scripted,resume_blocked=True)
        self.assertEqual(denied['reason'],'TASK_RESUME_NOT_AUTHORIZED')
        p=json.loads(self.path.read_text());p['automation_task_allowlist']=[result['task_id']]
        self.path.write_text(canonical(p))
        done=guarded_run(DOCS,self.root/'resume',self.store,self.policy,Scripted,resume_blocked=True)
        self.assertEqual(done['status'],'LOCAL_COMPLETE')
        def forbidden(p):raise AssertionError('no repeat')
        again=guarded_run(DOCS,self.root/'resume',self.store,self.policy,forbidden,resume_blocked=True)
        self.assertEqual(again['status'],'LOCAL_COMPLETE')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],2)

    def test_completed_json_repairs_missing_sqlite_completion_without_model(self):
        from mission import run
        run(DOCS,self.root/'repair',Scripted)
        def forbidden(p): raise AssertionError('model forbidden')
        result=guarded_run(DOCS,self.root/'repair',self.store,self.policy,forbidden,allow_model=False)
        self.assertEqual(result['status'],'LOCAL_COMPLETE')
        self.assertEqual(Durable(self.store).task(result['task_id'])['state'],'CONFIRMED')
        self.assertEqual(self.store.db.execute('SELECT state FROM automation_outbox').fetchone()[0],'PENDING')

    def test_technocore_retention_loss_is_explicit_and_snapshot_committed(self):
        class Reader:
            sandbox=False; origin='https://technocore.chat'
            def room(self,name):return self.origin+'/r/'+name
            def read(self,name):return {'room':name,'generation':1,'first_seq':self.first,'last_seq':self.last,'messages':[]}
        reader=Reader(); reader.first,reader.last=1,200
        discover(reader,self.store,now=NOW)
        reader.first,reader.last=250,450
        result=discover(reader,self.store,now=NOW+20)
        self.assertEqual(result['coverage']['retention_status'],'HISTORY_LOST')
        q=Durable(self.store)
        self.assertEqual(q.source(reader.room('tclk-offers'))['status'],'HISTORY_LOST')
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM events WHERE kind='discovery'").fetchone()[0],2)

    def test_actual_adapter_follows_only_server_next_page(self):
        root='https://api.github.com/orgs/flop-labs/repos?per_page=100&sort=updated'
        next_url='https://api.github.com/orgs/flop-labs/repos?per_page=100&page=2'
        class Reader:
            environment='sandbox'
            def __init__(self):self.calls=[]
            def read(self,url,timeout=5):
                self.calls.append(url)
                return {'body':'[]','status':200,'headers':{'Link':'<'+next_url+'>; rel="next"'} if url==root else {}}
        reader=Reader(); result=collect(self.store,reader=reader,roots=[('repositories',root)],now=NOW)
        self.assertEqual(reader.calls,[root,next_url])
        self.assertIsNone(Durable(self.store).source('sandbox_'+root)['cursor'])
        # First page advertised a next page; coverage conservatively stays partial, not a false global claim.
        self.assertFalse(result['check_complete'])

    def test_announcement_preserved_while_rulebook_down_and_closed_history(self):
        announcement='https://flop.finance/new-contest'; rulebook='https://flop.finance/rules'
        class Reader:
            environment='sandbox'
            def read(self,url,timeout=5):
                if url==rulebook:raise OSError('unavailable')
                return {'body':page(EVENT),'status':200,'headers':{}}
        roots=[('program_pages',announcement),('program_pages',rulebook)]
        result=collect(self.store,reader=Reader(),roots=roots,now=NOW)
        self.assertFalse(result['check_complete'])
        candidate=result['candidates'][0]
        self.assertEqual(candidate['checks']['reward_basis']['value'],'UNKNOWN')
        self.assertEqual(candidate['specification']['deadlines']['registration'],EVENT['registrationDeadline'])
        later=collect(self.store,reader=Reader(),roots=roots,now=NOW+30*86400)
        self.assertEqual(later['candidates'][0]['stage'],'HISTORY')
        self.assertEqual(later['candidates'][0]['specification']['results_and_claim_tracking'],'REVIEW_REQUIRED')

if __name__=='__main__':unittest.main()
