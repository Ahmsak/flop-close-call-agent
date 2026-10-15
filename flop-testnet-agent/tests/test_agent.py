import unittest
import agent

class GuardTests(unittest.TestCase):
    def test_execution_cannot_be_enabled_by_config(self):
        self.assertFalse(agent.readiness({'execution': True, 'evidence': dict.fromkeys(agent.REQUIRED, 'url')})['live_ready'])
        with self.assertRaisesRegex(RuntimeError, 'EXECUTION_DISABLED'):
            agent.execute(execute=True)

    def test_decimal_and_reserve(self):
        result = agent.plan({'budget': '1', 'reserve': '.1', 'unit': 'T', 'workloads': [
            {'name': 'a', 'count': 10, 'max_total_cost': '.3', 'unit': 'T'}]})
        self.assertEqual(result['tasks'][0]['planned'], 3)
        self.assertEqual(result['maximum_spend'], '0.9')

    def test_invalid_amounts(self):
        for value in ('NaN', 'Infinity', '-1'):
            with self.assertRaises(ValueError):
                agent.amount(value)

    def test_unknown_keeps_remaining_reservation(self):
        row = {'job_id': 'a', 'unit': 'T', 'state': 'unknown', 'max_total_cost': '5', 'paid': '1'}
        result = agent.audit([row])
        self.assertEqual(result['spent'], '1')
        self.assertEqual(result['still_reserved'], '4')
        with self.assertRaises(ValueError):
            agent.audit([row, row])

    def test_settled_claim_without_proof_does_not_count(self):
        row = {'job_id': 'a', 'unit': 'T', 'state': 'settled', 'max_total_cost': '5', 'paid': '5'}
        self.assertEqual(agent.audit([row])['locally_verified_independent_spend'], '0')
        self.assertEqual(agent.audit([row])['missing_settlement_evidence'], ['a'])

    def test_currency_mismatch(self):
        with self.assertRaises(ValueError):
            agent.plan({'budget': '10', 'reserve': '0', 'unit': 'T', 'workloads': [
                {'name': 'a', 'count': 1, 'max_total_cost': '1', 'unit': 'USD'}]})

    def test_overcharge(self):
        with self.assertRaises(ValueError):
            agent.audit([{'job_id': 'a', 'unit': 'T', 'state': 'settled', 'max_total_cost': '1', 'paid': '2'}])

if __name__ == '__main__':
    unittest.main()
