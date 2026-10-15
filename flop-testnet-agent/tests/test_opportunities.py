import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from opportunities import (EvidenceBook, assess, report, replay, selection, action_plan,
                           local_result, prepare_selected, from_offer, payment_contract_facts)
from ops import Store, Operator, Technocore, canonical, B58, digest
from jobs import discover
from sandbox import Venue, TestIdentity, grant_for

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT/'tests/fixtures/opportunities.json').read_text())

def book_for(case, now=FIXTURE['now']):
    book = EvidenceBook('sandbox')
    book.add(case['specification'], case['facts'], source='fixture://verified-contract', valid_until=now+600)
    return book

def fixed_test_identity():
    # Published RFC 8032 test vector, not a generated identity or an owner key.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    identity = object.__new__(TestIdentity)
    identity.key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(
        '9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60'))
    raw = b'\xed\x01'+identity.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    number, encoded = int.from_bytes(raw, 'big'), ''
    while number:
        number, remainder = divmod(number, 58)
        encoded = B58[remainder]+encoded
    identity.did, identity.nonce = 'did:key:z'+encoded, 0
    return identity

class ClassificationTests(unittest.TestCase):
    def test_source_outage_retains_official_candidates(self):
        from unittest.mock import Mock
        transport = Mock(sandbox=False, origin='https://technocore.chat')
        transport.read.side_effect = OSError('offline')
        result = discover(transport, Mock(), now=FIXTURE['now'])
        self.assertEqual(result['status'], 'SOURCE_UNAVAILABLE')
        self.assertEqual({c['category'] for c in result['candidates']}, {'B', 'C'})
        self.assertTrue(all(not c['can_execute'] for c in result['candidates']))

    def test_all_required_cases(self):
        for case in FIXTURE['cases']:
            with self.subTest(case=case['specification']['id']):
                c = assess(case['specification'], book_for(case), now=FIXTURE['now'])
                self.assertEqual(c['stage'], case['expected_stage'])
                self.assertEqual(c['checks']['permission']['value'], 'UNKNOWN')
                self.assertFalse(c['can_execute'])
                self.assertEqual(c['reward_received'], 'UNKNOWN')

    def test_contest_without_escrow_reaches_ready(self):
        case = FIXTURE['cases'][1]
        c = assess(case['specification'], book_for(case), now=FIXTURE['now'])
        self.assertEqual(c['stage'], 'READY')
        self.assertEqual(action_plan(c)['submission']['protocol'], 'technocore-signed-post')

    def test_arbitrary_ids_do_not_change_classification(self):
        for case in FIXTURE['cases']:
            case = copy.deepcopy(case)
            case['specification']['id'] = 'previously-unseen-'+str(len(case['specification']))
            self.assertEqual(assess(case['specification'], book_for(case), now=FIXTURE['now'])['stage'], case['expected_stage'])

    def test_self_asserted_proof_and_grant_not_trusted(self):
        case = copy.deepcopy(FIXTURE['cases'][0])
        case['specification'].update(verified=True, facts=case['facts'], permission=True)
        c = assess(case['specification'], EvidenceBook('sandbox'), now=FIXTURE['now'])
        self.assertEqual(c['checks']['reward_basis']['value'], 'UNKNOWN')
        self.assertEqual(c['stage'], 'DISCOVERED')

    def test_synthetic_proofs_cannot_load_into_live(self):
        case = FIXTURE['cases'][0]
        with self.assertRaisesRegex(ValueError, 'NOT_LIVE'):
            EvidenceBook('live').add(case['specification'], case['facts'], source='fixture://x', valid_until=1e12)
        self.assertEqual(assess(case['specification'], EvidenceBook('live'), now=FIXTURE['now'])['stage'], 'REJECTED')

    def test_proof_bound_to_entire_contract(self):
        case = copy.deepcopy(FIXTURE['cases'][0]); book = book_for(case)
        case['specification']['reward_terms']['amount'] = '1000000000'
        self.assertEqual(assess(case['specification'], book, now=FIXTURE['now'])['checks']['reward_basis']['value'], 'UNKNOWN')

    def test_stale_proof_or_observation_stops_ready(self):
        case = copy.deepcopy(FIXTURE['cases'][0])
        book = book_for(case)
        self.assertNotEqual(assess(case['specification'], book, now=FIXTURE['now']+301)['stage'], 'READY')
        c = assess(case['specification'], book, now=FIXTURE['now']+601)
        self.assertEqual(c['stage'], 'HISTORY')
        self.assertEqual(c['checks']['reward_basis']['value'], 'UNKNOWN')

    def test_role_alone_does_not_determine_direction(self):
        case = copy.deepcopy(FIXTURE['cases'][0])
        del case['facts']['direction']
        for hint in ('payer', 'payee'):
            case['specification']['role_hint'] = hint
            c = assess(case['specification'], book_for(case), now=FIXTURE['now'])
            self.assertEqual(c['checks']['direction']['value'], 'UNKNOWN')
            self.assertEqual(c['stage'], 'PREPARATION')

    def test_selection_prefers_ready_over_development_and_no_nominal_profit(self):
        candidates = [assess(c['specification'], book_for(c), now=FIXTURE['now']) for c in FIXTURE['cases']]
        picked = selection(candidates)
        self.assertEqual(picked['stage'], 'READY')
        unsupported = next(c for c in candidates if c['id']=='synthetic-unsupported')
        self.assertIn('MISSING_WORKER:image_annotation', action_plan(unsupported)['gaps'])
        self.assertIsNone(selection([c for c in candidates if c['stage']=='REJECTED']))

    def test_quality_failure_blocks_preparation(self):
        case = copy.deepcopy(FIXTURE['cases'][0]); case['specification']['acceptance']['expected']={'A':'wrong'}
        book=book_for(case); c=assess(case['specification'],book,now=FIXTURE['now'])
        with self.assertRaisesRegex(ValueError,'QUALITY'):
            local_result(c,book,now=FIXTURE['now'])

    def test_payment_evidence_must_match_contract_not_currency_name(self):
        spec=copy.deepcopy(FIXTURE['cases'][0]['specification'])
        terms={'payer':'buyer','beneficiary':'worker','asset':'TEST_USD','amount':'5'}
        spec['payment_contract']=terms
        record={**terms,'contract_hash':digest(terms),'locked_amount':'5','finalized':True,
                'status':'locked','valid_until':spec['deadline']}
        self.assertEqual(payment_contract_facts(spec,record)['value'],'YES')
        for key,value in [('beneficiary','someone-else'),('locked_amount','4'),('finalized',False),
                          ('status','claimed'),('valid_until',0),('contract_hash','forged')]:
            self.assertEqual(payment_contract_facts(spec,{**record,key:value})['value'],'UNKNOWN')

    def test_saved_real_34_are_regression_not_fixtures(self):
        # Freeze the original two discovery events, not the growing live journal.
        if not (ROOT/'runtime/state.sqlite').exists():
            self.skipTest('Private operational database intentionally excluded from review archive')
        source = Store(ROOT/'runtime/state.sqlite')
        try:
            source.diagnose()
            events = [json.loads(row['evidence']) for row in source.db.execute(
                "SELECT evidence FROM events WHERE kind='discovery' AND seq IN (1,2) ORDER BY seq")]
        finally:
            source.close()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = Store(Path(folder.name)/'regression.sqlite', create=True)
        for event in events:
            store.record('', 'discovery', event)
        try:
            before = store.diagnose()
            with patch('ops.Technocore.request', side_effect=AssertionError('network forbidden')):
                result = replay(store, now=FIXTURE['now'])
            actual = [c for c in result['candidates'] if c['category']=='A']
            self.assertEqual(len(actual), 34)
            paper = [c for c in actual if c['checks']['reward_basis']['reason']=='PAPER_RAIL_HAS_NO_VALUE']
            self.assertEqual(len(paper),33)
            other = [c for c in actual if c not in paper]
            self.assertEqual(len(other),1)
            self.assertEqual(other[0]['checks']['direction']['value'],'UNKNOWN')
            self.assertEqual(other[0]['checks']['reward_basis']['value'],'UNKNOWN')
            self.assertEqual(len([c for c in result['candidates'] if c['category']=='B' and c['stage']=='HISTORY']),2)
            self.assertEqual(next(c for c in result['candidates'] if c['category']=='C')['stage'],'PREPARATION')
            self.assertEqual(before,store.diagnose())
        finally:
            store.close()

class ExecutorBridgeTests(unittest.TestCase):
    def test_positive_order_and_contest_to_existing_executor(self):
        summary=[]
        for index in (0,1):
            with tempfile.TemporaryDirectory() as folder, Venue() as venue:
                case=copy.deepcopy(FIXTURE['cases'][index]); now=time.time()
                spec=case['specification']; spec.update(observed_at=now,deadline=now+120)
                spec['submission']['origin']=venue.origin
                identity=fixed_test_identity(); state=Store(Path(folder)/'state.sqlite',create=True)
                try:
                    # Isolated review adapter authenticates source and funding independently.
                    frame={'type':'offer','id':spec['id'],'from':identity.did,'role':'payer',
                           'expiresMs':int(spec['deadline']*1000)}
                    source_row=venue.append('tclk-offers',identity.envelope('tclk-offers','tclk1 '+canonical(frame)))
                    spec['source_record']=source_row
                    if index==0:
                        terms={'payer':'fixture-buyer','beneficiary':identity.did,'asset':'TEST_USD','amount':'5'}
                        spec['payment_contract']=terms
                        rail_record={**terms,'contract_hash':digest(terms),'locked_amount':'5','finalized':True,
                                     'status':'locked','valid_until':spec['deadline']}
                        case['facts']['reward_basis']=payment_contract_facts(spec,rail_record)
                    book=book_for(case,now)
                    transport=Technocore(venue.origin,sandbox=True)
                    found=discover(transport,state,now=now,reviewed=([spec],book))
                    self.assertEqual(len(found['eligible']),1)
                    selected=selection(found['candidates']); plan=action_plan(selected)
                    self.assertEqual(plan['gaps'],['Prepare exact envelope, then use executor owner-grant check'])
                    result=local_result(selected,book,now=now)
                    operator=Operator(state,Technocore(venue.origin,sandbox=True),identity.did)
                    envelope=identity.envelope('delivery',canonical(result))
                    operation=prepare_selected(selected,book,operator,envelope)
                    with self.assertRaises(PermissionError):operator.execute(operation)
                    self.assertEqual(venue.posts,0)
                    receipt=operator.execute(operation,grant_for(operator,operation))
                    self.assertEqual(receipt['state'],'CONFIRMED')
                    self.assertEqual(venue.posts,1)
                    operator.execute(operation)
                    self.assertEqual(venue.posts,1)
                    summary.append({'category':spec['category'],'stage':selected['stage'],
                                    'without_grant':'BLOCKED','with_sandbox_grant':receipt['state'],
                                    'posts':venue.posts,'reward_received':'UNKNOWN'})
                    with self.assertRaises(PermissionError):
                        prepare_selected(selected,EvidenceBook('replay'),operator,envelope)
                finally:state.close()
        print('DISCOVERY_BRIDGE_SANDBOX '+json.dumps(summary))

if __name__=='__main__':unittest.main()
