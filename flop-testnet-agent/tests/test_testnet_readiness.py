import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import agent
import testnet_readiness as launch
from ops import Store, strict_json
from source_discovery import official

class Reader:
    environment='sandbox'
    def __init__(self): self.calls=[]; self.fail=False
    def read(self,url,timeout):
        self.calls.append(url)
        if self.fail: raise TimeoutError('no response')
        return {'status':200,'body':'<style>fake launch</style><h1>testnet (planned)</h1>'}

class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.profile=strict_json(launch.PROFILE.read_text())
        self.observations=[{'url':u,'status':'OK','observed_at':100,'text':'testnet (live)'} for u in launch.SOURCES]
    def evaluate(self):return launch.evaluate(self.profile,self.observations,now=100)
    def test_empty_genesis_and_separate_profile(self):
        self.assertIn('MISSING_GENESIS',self.evaluate()['reasons'])
        self.assertTrue(all(self.profile[k] is None for k in launch.FIELDS))
        self.assertNotIn('devnet',json.dumps(self.profile))
    def test_forged_launch_source(self):
        self.observations[0]['url']='https://evil.example/launch'
        self.assertIn('UNTRUSTED_SOURCE',self.evaluate()['reasons'])
        self.assertFalse(self.evaluate()['can_execute'])
    def test_wrong_network(self):
        self.profile['network']='devnet'
        self.assertIn('WRONG_NETWORK',self.evaluate()['reasons'])
    def test_outdated_sdk(self):
        self.profile['required_cli']='0.5.0'
        self.assertIn('SDK_NOT_QUALIFIED',self.evaluate()['reasons'])
    def test_closed_faucet(self):
        self.profile['faucet_status']='CLOSED'
        self.assertIn('FAUCET_CLOSED',self.evaluate()['reasons'])
    def test_conflicting_sources(self):
        self.observations[1]['text']='testnet (planned)'
        self.assertIn('SOURCE_CLAIMS_REQUIRE_RECONCILIATION',self.evaluate()['reasons'])
    def test_calendar_and_single_200_not_open(self):
        self.observations=self.observations[:1]
        r=launch.evaluate(self.profile,self.observations,now=1793664000)
        self.assertEqual(r['testnet_open'],'UNKNOWN')
        self.assertIn('COVERAGE_INCOMPLETE',r['reasons'])
    def test_complete_fabricated_profile_never_authorizes(self):
        self.profile.update({k:'invented' for k in launch.FIELDS})
        self.profile.update(status='VERIFIED',genesis='0x'+'a'*64,required_cli='0.4.0',faucet_status='OPEN')
        self.assertEqual(self.evaluate()['status'],'UNVERIFIED')
        self.assertFalse(self.evaluate()['can_execute'])
    def test_future_and_stale_observation(self):
        for stamp in (101,-1000):
            self.observations[0]['observed_at']=stamp
            self.assertIn('SOURCE_STALE_OR_FUTURE',self.evaluate()['reasons'])
    def test_allowlist_no_faucet_or_arbitrary_docs(self):
        self.assertTrue(all(official(u) for u in launch.SOURCES))
        self.assertFalse(official('https://faucet.flop.network/chain'))
        self.assertFalse(official('https://docs.flop.network/anything'))
    def test_durable_restart_dedup_and_failure_keeps_success_time(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.sqlite';s=Store(p,create=True);reader=Reader()
            r=launch.check(reader=reader,store=s,now=100)
            self.assertEqual(reader.calls,list(launch.SOURCES))
            self.assertEqual(len(r['candidates']),5)
            self.assertNotIn('fake launch',r['sources'][0]['text'])
            n=s.db.execute('SELECT count(*) FROM automation_events').fetchone()[0];s.close()
            s=Store(p)
            try:
                launch.check(reader=reader,store=s,now=110)
                self.assertEqual(n,s.db.execute('SELECT count(*) FROM automation_events').fetchone()[0])
                reader.fail=True;launch.check(reader=reader,store=s,now=120)
                self.assertEqual(s.db.execute('SELECT last_success FROM automation_sources LIMIT 1').fetchone()[0],110)
            finally:s.close()
    def test_cli_does_not_open_default_store_or_config(self):
        with patch('testnet_readiness.PublicReader',return_value=Reader()), patch('sys.argv',['agent.py','testnet-readiness']), patch('ops.Store',side_effect=AssertionError('private store')), contextlib.redirect_stdout(io.StringIO()) as out:
            agent.main()
        self.assertEqual(json.loads(out.getvalue())['execution'],'EXECUTION_DISABLED')
