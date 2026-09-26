import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch
import urllib.error

from tools.contest_client import observer as o
from tools.contest_client.validation import validated_replay,PartialArchiveError
from tools.simulate_strategy import simulate
from tools.contest_client import ContestClient
from tools.research_scenarios import compare_finals,final_scenarios
from test_tooling import scenario

NOW=dt.datetime(2026,9,25,12,6,tzinfo=dt.timezone.utc)


def envelope(body,seq=1,signer=o.EXPECTED_SIGNER):
    return {'seq':seq,'ts':'2026-09-25T12:05:00Z','from':signer,'nonce':seq,'text':json.dumps(body),'sig':'MOCK_ONLY_NOT_SIGNATURE'}


def fixtures():
    bodies={'price':{'ref':{'px':'100','time':'2026-09-25T12:05:00Z','tid':1},'global':'99'},
            'flow':{'mints':['did:key:z6Mk'+'A'*44],'settled':['trade-id-only'],'void':[],
                    'omitted':{'mints':9,'settled':5},'missed':[['close1',1,5]]},
            'state':{'owners':10},'positions':{'open':'1','top':[]},'pnl':{'mark':'99','top':[]}}
    result={}
    for room in o.ROOMS:
        kind=room.removeprefix('d-close1-');body={'t':kind,'n':1,'file':'a'*64,**bodies[kind]}
        rows=[envelope(body)]
        if kind=='price':
            rows=[envelope({'t':'seed','season':'close-1','package':o.MANIFEST_SHA}),envelope(body,2)]
        result[room]=('\n'.join(json.dumps(r) for r in rows)+'\n').encode()
    return result


def fake_verify(room,row):return row['from']


def change(raw,room,fn):
    rows=[json.loads(l) for l in raw[room].splitlines()]
    fn(rows)
    raw[room]=('\n'.join(json.dumps(r) for r in rows)+'\n').encode()


class ObserverTests(unittest.TestCase):
    def analyze(self,raw=None,**kw):return o.analyze(raw or fixtures(),now=NOW,verifier=fake_verify,**kw)
    def test_partial_counts_not_people(self):
        s=self.analyze();self.assertEqual(s['status'],'PARTIAL')
        self.assertEqual(s['counts']['declared_owner_accounts'],10)
        self.assertEqual(s['counts']['explicit_mint_accounts'],1)
        self.assertEqual(s['counts']['observed_unique_accounts'],1)
        self.assertIsNone(s['counts']['explicit_settled_trade_accounts'])
        self.assertIsNone(s['counts']['humans']);self.assertFalse(s['trust']['LEDGER_REPLAY_VERIFIED'])
        self.assertEqual(s['counts']['reported_settled_trades'],6)
    def test_missing_room_no_common(self):
        raw=fixtures();del raw['d-close1-state']
        self.assertEqual(self.analyze(raw)['reason'],'NO_COMMON_SWEEP')
    def test_manifest_mismatch_rejected(self):
        raw=fixtures()
        def mutate(rows):
            b=json.loads(rows[0]['text']);b['package']='0'*64;rows[0]['text']=json.dumps(b)
        change(raw,'d-close1-price',mutate)
        result=self.analyze(raw)
        self.assertEqual(result['status'],'REJECTED')
        self.assertTrue(result['trust']['SEED_SIGNATURE_VALID'])
        self.assertFalse(result['trust']['MANIFEST_HASH_MATCH'])
    def test_local_pin_mismatch(self):
        result=self.analyze(pin_valid=False)
        self.assertEqual(result['status'],'REJECTED');self.assertFalse(result['trust']['RULES_COMMIT_PINNED'])
    def test_invalid_signature(self):
        def invalid(*args):raise ValueError('bad_signature')
        result=o.analyze(fixtures(),now=NOW,verifier=invalid)
        self.assertEqual(result['status'],'REJECTED');self.assertFalse(result['trust']['SEED_SIGNATURE_VALID'])
    def test_negative_omission(self):
        raw=fixtures()
        def mutate(rows):
            b=json.loads(rows[0]['text']);b['omitted']['mints']=-1;rows[0]['text']=json.dumps(b)
        change(raw,'d-close1-flow',mutate)
        self.assertEqual(self.analyze(raw)['status'],'REJECTED')
    def test_key_rotation_rejected(self):
        raw=fixtures();change(raw,'d-close1-flow',lambda rows:rows[0].update({'from':'unconfirmed-key'}))
        self.assertEqual(self.analyze(raw)['status'],'REJECTED')
    def test_after_final_rejected(self):
        raw=fixtures()
        def mutate(rows):
            rows.insert(1,envelope({'t':'final','price':'100'},2));rows[-1]['seq']=3;rows[-1]['nonce']=3
        change(raw,'d-close1-price',mutate)
        self.assertEqual(self.analyze(raw)['status'],'REJECTED')
    def test_duplicate_sweep_rejected(self):
        raw=fixtures()
        def mutate(rows):
            r=copy.deepcopy(rows[-1]);r.update(seq=2,nonce=2);rows.append(r)
        change(raw,'d-close1-flow',mutate)
        self.assertEqual(self.analyze(raw)['status'],'REJECTED')
    def test_seq_gap_visible(self):
        raw=fixtures();change(raw,'d-close1-flow',lambda rows:rows[0].update(seq=4))
        self.assertEqual(self.analyze(raw)['gaps']['d-close1-flow'],[[1,3]])
    def test_hash_disagreement_rejected(self):
        raw=fixtures()
        def mutate(rows):
            b=json.loads(rows[0]['text']);b['file']='b'*64;rows[0]['text']=json.dumps(b)
        change(raw,'d-close1-state',mutate)
        self.assertEqual(self.analyze(raw)['status'],'REJECTED')
    def test_newer_sweep_not_mixed(self):
        raw=fixtures()
        def mutate(rows):
            b=json.loads(rows[0]['text']);b.update(n=2,owners=999);rows.append(envelope(b,2))
        change(raw,'d-close1-state',mutate)
        s=self.analyze(raw);self.assertTrue(s['cross_room_lag']);self.assertEqual(s['counts']['declared_owner_accounts'],10)
    def test_stale_labeled(self):
        s=o.analyze(fixtures(),now=NOW+dt.timedelta(hours=1),verifier=fake_verify)
        self.assertTrue(s['stale'])
    def test_client_recomputes_staleness_on_read(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'snapshot.json';s=self.analyze();s['timestamp']='2000-01-01T00:00:00Z';s['sweep_timestamp']=s['timestamp']
            p.write_text(json.dumps(s))
            self.assertTrue(ContestClient(p).get_leaderboard()['stale'])
    def test_truncated_json_rejected(self):
        raw=fixtures();raw['d-close1-flow']+=b'{"seq":2'
        self.assertEqual(self.analyze(raw)['status'],'REJECTED')
    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError):o.strict_json('{"n":1,"n":2}')
    def test_atomic_failure_keeps_previous(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';p.write_text('original')
            with patch.object(o.os,'replace',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):o.atomic_write(p,b'new')
            self.assertEqual(p.read_text(),'original');self.assertEqual(len(list(Path(d).iterdir())),1)
    def test_rejected_refresh_does_not_promote(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'latest.json';p.write_text('original')
            with patch.object(o,'local_pin_valid',return_value=True):
                o.refresh(d,fetcher=lambda room:(None,{'room':room,'error':'unavailable'}))
            self.assertEqual(p.read_text(),'original')
    def test_real_public_seed_signature_and_tamper(self):
        row=json.loads((Path(__file__).parent/'fixtures/public_seed.json').read_text())
        self.assertEqual(o.verify_record('d-close1-price',row),o.EXPECTED_SIGNER)
        row['text']+=' '
        with self.assertRaises(Exception):o.verify_record('d-close1-price',row)


class TransportTests(unittest.TestCase):
    class Response(io.BytesIO):
        status=200;headers={}
    def test_size_limit(self):
        class Opener:
            def open(self,*a,**kw):return TransportTests.Response(b'12345')
        raw,meta=o.fetch('close1',opener=Opener(),max_bytes=4)
        self.assertIsNone(raw);self.assertEqual(meta['error'],'response_size_limit')
    def test_auth_no_retry(self):
        calls=[]
        class Opener:
            def open(self,*a,**kw):
                calls.append(1);raise urllib.error.HTTPError('url',401,'auth',{},None)
        self.assertIsNone(o.fetch('close1',opener=Opener())[0]);self.assertEqual(len(calls),1)
    def test_timeout_bounded_backoff(self):
        waits=[]
        class Opener:
            def open(self,*a,**kw):raise TimeoutError()
        raw,meta=o.fetch('close1',opener=Opener(),sleep=waits.append)
        self.assertEqual(waits,[1,2]);self.assertEqual(meta['attempts'],3)
    def test_write_endpoint_denied(self):
        with self.assertRaises(ValueError):o.fetch('close1/say/name/text')
    def test_redirect_disabled(self):self.assertIsNone(o.NoRedirect().redirect_request(None,None,None,None,None,None))


class ReplayTests(unittest.TestCase):
    def events(self):return [{'t':'seed','px':'100'},{'t':'sweep','n':1,'ref':'100','close':'100','owners':[],'trades':[]},{'t':'final','px':'101'}]
    def test_terminal_phase(self):
        e=self.events();e.append(e[1])
        with self.assertRaisesRegex(ValueError,'event_after_final'):validated_replay(e,{'lock_sweep':1})
    def test_missing_archive(self):
        with self.assertRaises(PartialArchiveError):validated_replay(self.events())
    def test_missing_sweep(self):
        e=self.events();e[1]['n']=2
        with self.assertRaisesRegex(PartialArchiveError,'missing_sweep'):validated_replay(e,{'lock_sweep':2})
    def test_sweep_order(self):
        e=self.events();e.insert(2,e[1])
        with self.assertRaisesRegex(ValueError,'sweep_order'):validated_replay(e,{'lock_sweep':1})
    def test_complete_small_fixture(self):self.assertEqual(validated_replay(self.events(),{'lock_sweep':1})['final']['S'],'101')
    def test_live_final_distinction(self):
        r=simulate(scenario(final='120.00'))
        self.assertEqual(r['history'][0]['live_score'],'-10.0000')
        self.assertEqual(r['accounts'][0]['contest_score'],'190.0000')
    def test_no_counterparty_no_fill(self):
        s=scenario();s['sweeps'][0]['trades'][0]['counterparty_available']=False
        r=simulate(s);self.assertEqual(r['accounts'][0]['contest_score'],'0');self.assertEqual(r['not_submitted'][0]['reason'],'NO_COUNTERPARTY')
    def test_late_account_preconfirmed(self):
        r=simulate(final_scenarios()['late_confirmed_long'])
        self.assertEqual(len(r['sweeps'][0]['minted']),2)
        self.assertEqual(r['sweeps'][1]['minted'],[])
        self.assertEqual(r['sweeps'][1]['trades'][0]['outcome'],'settled')
    def test_delay_fee_and_void_scenarios(self):
        cases=final_scenarios()
        self.assertEqual(Decimal(simulate(cases['delay_clawback'])['accounts'][0]['contest_score']),Decimal('-40'))
        self.assertEqual(simulate(cases['expired'])['sweeps'][-1]['trades'][0]['reason'],'expired')
        self.assertEqual(simulate(cases['insufficient_reserve'])['sweeps'][0]['trades'][0]['reason'],'funds')
