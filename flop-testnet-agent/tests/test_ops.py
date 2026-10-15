import copy
import json
from pathlib import Path
import tempfile
import time
import unittest

from ops import Operator, Store, Technocore, canonical, digest, verify_record
from sandbox import TestIdentity, Venue, demo, grant_for
from jobs import choose, discover, solve

class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'state.sqlite'
        self.store = Store(self.path, create=True)
        self.venue = Venue().__enter__()
        self.owner = TestIdentity()
        self.transport = Technocore(self.venue.origin, sandbox=True)
        self.operator = Operator(self.store, self.transport, self.owner.did)

    def tearDown(self):
        self.store.close()
        self.venue.__exit__()
        self.temp.cleanup()

    def prepare(self):
        return self.operator.prepare('job-1', 'delivery', self.owner.envelope('delivery', 'result'),
                                     valid_until=time.time()+120, source_seen_at=time.time())

    def test_restart_after_lost_reply_does_not_resend(self):
        operation = self.prepare()
        grant = grant_for(self.operator, operation)
        self.venue.drop_reply = True
        self.assertEqual(self.operator.execute(operation, grant)['state'], 'UNKNOWN')
        self.store.close()
        self.store = Store(self.path)
        self.operator = Operator(self.store, self.transport, self.owner.did)
        self.assertEqual(self.operator.execute(operation, grant)['state'], 'CONFIRMED')
        self.assertEqual(self.venue.posts, 1)

    def test_no_receipt_is_unknown_not_resend(self):
        operation = self.prepare()
        grant = grant_for(self.operator, operation)
        self.venue.drop_reply = True
        self.operator.execute(operation, grant)
        self.venue.hide_records = True
        for _ in range(3):
            self.assertEqual(self.operator.execute(operation, grant)['state'], 'UNKNOWN')
        self.assertEqual(self.venue.posts, 1)

    def test_crash_after_write_ahead_before_network_is_unknown(self):
        operation = self.prepare()
        with self.store.db:
            self.store.db.execute("UPDATE operations SET state='SENDING' WHERE id=?", (operation,))
        self.assertEqual(self.operator.execute(operation, grant_for(self.operator, operation))['state'], 'UNKNOWN')
        self.assertEqual(self.venue.posts, 0)

    def test_no_permission_or_wrong_scope_never_sends(self):
        operation = self.prepare()
        with self.assertRaises(PermissionError):
            self.operator.execute(operation)
        for key, value in [('environment', 'live'), ('room', 'other'), ('max_spend', '1'),
                           ('expires_at', 0), ('request_hash', 'bad'), ('did', 'other'), ('max_writes', 2)]:
            grant = grant_for(self.operator, operation)
            grant[key] = value
            with self.assertRaises(PermissionError):
                self.operator.execute(operation, grant)
        self.assertEqual(self.venue.posts, 0)

    def test_sources_down_stop_first_send_and_preserve_pending(self):
        operation = self.prepare()
        self.venue.fail_reads = True
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_UNAVAILABLE'):
            self.operator.execute(operation, grant_for(self.operator, operation))
        self.assertEqual(self.venue.posts, 0)
        self.assertEqual(discover(self.transport, self.store)['status'], 'SOURCE_UNAVAILABLE')
        self.venue.fail_reads = False
        self.venue.drop_reply = True
        self.operator.execute(operation, grant_for(self.operator, operation))
        self.venue.fail_reads = True
        self.assertEqual(self.operator.verify(operation)['state'], 'UNKNOWN')

    def test_stale_preparation_and_execution(self):
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.operator.prepare('old', 'delivery', self.owner.envelope('delivery', 'x'),
                                  valid_until=time.time()+100, source_seen_at=time.time()-301)
        operation = self.prepare()
        self.operator.clock = lambda: time.time()+301
        grant = grant_for(self.operator, operation)
        grant['expires_at'] = time.time()+600
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.operator.execute(operation, grant)
        self.assertEqual(self.venue.posts, 0)

    def test_room_recreated_does_not_prove_original_delivery(self):
        operation = self.prepare()
        self.venue.drop_reply = True
        self.operator.execute(operation, grant_for(self.operator, operation))
        self.venue.generation += 1
        self.assertEqual(self.operator.verify(operation)['state'], 'UNKNOWN')

    def test_changed_job_cannot_create_second_operation(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'already prepared'):
            self.prepare()

    def test_second_database_connection_does_not_resend(self):
        operation = self.prepare()
        self.operator.execute(operation, grant_for(self.operator, operation))
        other_store = Store(self.path)
        try:
            other = Operator(other_store, self.transport, self.owner.did)
            self.assertEqual(other.execute(operation)['state'], 'CONFIRMED')
            self.assertEqual(self.venue.posts, 1)
        finally:
            other_store.close()

    def test_missing_state_requires_explicit_recovery(self):
        with self.assertRaisesRegex(RuntimeError, 'STATE_MISSING'):
            Store(Path(self.temp.name)/'missing.sqlite')
        with self.assertRaises(RuntimeError):
            Store(self.path, create=True)
        self.store.backup(Path(self.temp.name)/'backup.sqlite')
        recovered = Store(Path(self.temp.name)/'backup.sqlite')
        self.assertEqual(recovered.diagnose()['sqlite'], 'ok')
        recovered.close()

    def test_evidence_tampering_detected(self):
        self.prepare()
        with self.store.db:
            self.store.db.execute("UPDATE events SET evidence='{}' WHERE seq=1")
        with self.assertRaisesRegex(RuntimeError, 'EVIDENCE_CORRUPT'):
            self.store.diagnose()

    def test_signed_body_tampering_rejected(self):
        envelope = self.owner.envelope('delivery', 'original')
        envelope['text'] = 'changed'
        with self.assertRaises(Exception):
            self.operator.prepare('bad', 'delivery', envelope,
                                  valid_until=time.time()+100, source_seen_at=time.time())

    def test_database_cannot_switch_identity(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'MISMATCH'):
            Operator(self.store, self.transport, TestIdentity().did)

    def test_live_transport_rejects_sandbox_grant_before_network(self):
        operation = self.prepare()
        from ops import strict_json
        request = strict_json(self.store.get(operation)['request'])
        with self.assertRaises(PermissionError):
            Technocore().publish(request, grant_for(self.operator, operation), time.time())

    def test_control_characters_rejected_before_publish(self):
        with self.assertRaisesRegex(ValueError, 'sanitation'):
            self.operator.prepare('bad', 'delivery', self.owner.envelope('delivery', 'one\ntwo'),
                                  valid_until=time.time()+100, source_seen_at=time.time())

    def test_redirect_and_mutating_read_paths_not_available(self):
        for origin in ('https://evil.test', 'http://localhost:80', self.venue.origin+'/r/x'):
            with self.assertRaises(ValueError):
                Technocore(origin)
        with self.assertRaises(ValueError):
            self.transport.read('room/say/name/text')

    def test_reward_requires_matching_verified_requester(self):
        requester = TestIdentity()
        result = {'A': '1'}
        operation = self.operator.prepare('job-1', 'delivery', self.owner.envelope('delivery', canonical({'result': result})),
                                          valid_until=time.time()+100, source_seen_at=time.time())
        self.operator.execute(operation, grant_for(self.operator, operation))
        fake = {'kind': 'local-job-accepted-v1', 'operation': operation,
                'result_hash': digest(result), 'reward': '10', 'unit': 'PAPER'}
        self.venue.append('delivery', self.owner.envelope('delivery', canonical(fake)))
        self.assertEqual(self.operator.reward(operation, requester.did)['status'], 'UNKNOWN')
        fake['operation'] = 'different'
        self.venue.append('delivery', requester.envelope('delivery', canonical(fake)))
        self.assertEqual(self.operator.reward(operation, requester.did)['status'], 'UNKNOWN')
        self.venue.fail_reads = True
        self.assertEqual(self.operator.reward(operation, requester.did)['status'], 'UNKNOWN')

class WorkloadTests(unittest.TestCase):
    def test_model_unavailable_has_bounded_fallback(self):
        def unavailable(_):
            raise ConnectionError('model down')
        jobs = [{'id': 'one', 'reward': '1', 'unit': 'PAPER', 'deadline': 1},
                {'id': 'two', 'reward': '2', 'unit': 'PAPER', 'deadline': 2}]
        selected, reason = choose(jobs, unavailable)
        self.assertEqual(selected['id'], 'two')
        self.assertEqual(reason, 'model_unavailable_fallback')

    def test_bounded_real_computation_without_llm(self):
        job = {'workload': 'invoice_totals_v1', 'input': 'sku,quantity,unit_price\nX,3,0.10\nX,2,0.20\n'}
        self.assertEqual(solve(job), {'X': '0.70'})
        job['input'] = 'x'*65537
        with self.assertRaises(ValueError):
            solve(job)

    def test_full_run(self):
        with tempfile.TemporaryDirectory() as folder:
            result = demo(folder)
            self.assertEqual(result['after_lost_response'], 'UNKNOWN')
            self.assertEqual(result['after_restart'], 'CONFIRMED')
            self.assertTrue(result['resumed_in_separate_process'])
            self.assertEqual(result['post_count'], 1)
            self.assertEqual(result['reward_status'], 'SANDBOX_ACCEPTED')
            self.assertEqual(result['money_received'], '0')
            store = Store(Path(folder)/'state.sqlite')
            self.assertEqual(store.diagnose()['operations'][0]['state'], 'ACCEPTED')
            store.close()

if __name__ == '__main__':
    unittest.main()
