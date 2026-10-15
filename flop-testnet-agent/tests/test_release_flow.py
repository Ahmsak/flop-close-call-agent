"""Offline subprocess acceptance; synthetic database, input and lost delivery reply."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from automation_demo import DeliveryFixture
from durable import Durable
from ops import Store, canonical


class ReleaseFlowTests(unittest.TestCase):
    def test_event_worker_crash_outbox_and_process_restart(self):
        component=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            policy={'execution':'EXECUTION_DISABLED','owner_did':'synthetic',
                    'real_money_budget':'0','automation_daily_units':{'local':2},
                    'automation_sandbox_delivery':True}
            (root/'policy.json').write_text(canonical(policy),encoding='utf-8')
            store=Store(root/'state.sqlite',create=True)
            job=json.loads((component/'examples/job.json').read_text())
            Durable(store,clock=lambda:100).page('sandbox:invoice',None,'1',
                [{'id':'synthetic-invoice','job':job}],{'environment':'SANDBOX'},event_kind='synthetic_input')
            store.close()
            command=[sys.executable,str(component/'automation_demo.py'),'--worker',str(root),'--now']
            first=subprocess.run(command+['100','--crash'],capture_output=True,text=True)
            self.assertEqual(first.returncode,17,first.stderr)
            second=subprocess.run(command+['131'],capture_output=True,text=True)
            self.assertEqual(second.returncode,0,second.stderr)
            store=Store(root/'state.sqlite')
            try:
                q=Durable(store,clock=lambda:132)
                task=dict(q.db.execute('SELECT * FROM automation_tasks').fetchone())
                self.assertEqual(json.loads(task['spec'])['input'],job)
                self.assertEqual(task['state'],'CONFIRMED')
                notice=dict(q.db.execute('SELECT * FROM automation_outbox').fetchone())
                self.assertEqual(notice['state'],'UNKNOWN')
                fixture=DeliveryFixture(root/'fake-service.json')
                self.assertEqual(q.reconcile_notice(notice['id'],fixture)['state'],'SERVICE_ACCEPTED')
                ids=(task['id'],notice['id'])
            finally:store.close()
            third=subprocess.run(command+['140'],capture_output=True,text=True)
            self.assertEqual(third.returncode,0,third.stderr)
            store=Store(root/'state.sqlite')
            try:
                q=Durable(store)
                self.assertEqual(q.db.execute('SELECT COUNT(*) FROM automation_events').fetchone()[0],1)
                self.assertEqual(q.db.execute('SELECT COUNT(*) FROM automation_actions').fetchone()[0],1)
                self.assertEqual(q.db.execute('SELECT id FROM automation_tasks').fetchone()[0],ids[0])
                self.assertEqual(q.db.execute('SELECT id FROM automation_outbox').fetchone()[0],ids[1])
                self.assertEqual(fixture.lookup(ids[1])['send_count'],1)
                self.assertEqual(q.health()['user_read_confirmation'],'UNKNOWN')
                self.assertEqual(store.diagnose()['sqlite'],'ok')
                print('RELEASE_FLOW_OFFLINE: events=1 tasks=1 calculations=1 notices=1 fixture_sends=1 '
                      'restart=preserved live_calls=0 user_read=UNKNOWN')
            finally:store.close()
