import json
from pathlib import Path
import tempfile
import unittest

from mission import run, check_brief, model_command, MAX_STEPS

DOCS={'s':{'source':'https://flop.finance/testnet/', 'observed_at':1,
           'text':'Enrollment requires a published procedure. No reward is guaranteed for posting messages.'}}
BRIEF={'title':'Procedure gap','beneficiary':'Operator','need':'Avoid unsupported enrollment claims',
       'plan':['Read','Check source claims'], 'claims':[
           {'statement':'Procedure required','document':'s','quote':'Enrollment requires a published procedure.'},
           {'statement':'Posting has no guaranteed reward','document':'s','quote':'No reward is guaranteed for posting messages.'}],
       'limitations':['Synthetic unit test, not live evidence'], 'next_action':'Wait for published enrollment procedure'}

class Scripted:
    def __init__(self, path): self.calls=0
    def decide(self, context, step, remaining):
        self.calls+=1
        if step==1: tool,args='read',{'document':'s'}
        else: tool,args='write',BRIEF
        return {'tool':tool,'reason':'TEST_DOUBLE','arguments':json.dumps(args)},[]

class MissionTests(unittest.TestCase):
    def test_complete_restart_and_artifact_loss(self):
        with tempfile.TemporaryDirectory() as path:
            result=run(DOCS,path,Scripted)
            self.assertEqual(result['status'],'LOCAL_COMPLETE')
            def forbidden(path): raise AssertionError('restart must not call model')
            self.assertEqual(run(DOCS,path,forbidden)['status'],'LOCAL_COMPLETE')
            (Path(path)/'result.html').unlink()
            self.assertEqual(run(DOCS,path,forbidden)['status'],'ARTIFACT_MISSING_OR_CHANGED')

    def test_quotes_checked_against_read_sources(self):
        self.assertFalse(check_brief(BRIEF,DOCS,[])['passed'])
        changed={'s':{**DOCS['s'],'text':'Different conditions entirely'}}
        self.assertFalse(check_brief(BRIEF,changed,['s'])['passed'])

    def test_untrusted_tool_cannot_execute_and_budget_stops(self):
        class Attack(Scripted):
            def decide(self,*args): return {'tool':'shell','arguments':'{}','reason':'malicious source'},[]
        with tempfile.TemporaryDirectory() as path:
            result=run(DOCS,path,Attack)
            self.assertEqual(result['status'],'BUDGET_EXHAUSTED')
            self.assertEqual(len(result['steps']),MAX_STEPS)
            self.assertTrue(all(step['outcome']=='REJECTED' for step in result['steps']))

    def test_provider_failure_has_no_fallback(self):
        def offline(path): raise RuntimeError('MODEL_UNAVAILABLE')
        with tempfile.TemporaryDirectory() as path:
            result=run(DOCS,path,offline)
            self.assertEqual(result['status'],'BLOCKED')
            self.assertEqual(result['steps'],[])

    def test_interrupted_decision_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as path:
            result=run(DOCS,path,Scripted)
            result.update(status='RUNNING',steps=[{'outcome':'IN_FLIGHT'}])
            (Path(path)/'state.json').write_text(json.dumps(result),encoding='utf-8')
            self.assertEqual(run(DOCS,path,Scripted)['status'],'UNKNOWN_MODEL_RESPONSE')

    def test_cli_permissions_not_prompt_only(self):
        command=model_command('codex','schema','output')
        self.assertIn('features.shell_tool=false',command)
        self.assertIn('forced_login_method="chatgpt"',command)
        self.assertIn('--ignore-user-config',command)
        self.assertIn('read-only',command)

if __name__=='__main__':unittest.main()
