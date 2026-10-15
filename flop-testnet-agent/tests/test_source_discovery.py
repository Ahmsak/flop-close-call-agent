import copy
import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

from ops import Store
from source_discovery import collect, extract, journal, PublicReader, MAX_BYTES, TTL, official

NOW = 1791975000
URL = 'https://flop.finance/announcements/'
MIRROR = 'https://flop.finance/news/'
EVENT = {'@context': 'https://schema.org', '@type': 'Event',
         '@id': 'https://github.com/flop-labs/unknown-orbital-782-contest',
         'name': 'Previously unseen Orbital 782 Contest',
         'description': 'Prize: 700 FLOP after mainnet, subject to jury acceptance. Task: unsupported orbital proof.',
         'startDate': '2026-10-15T00:00:00Z', 'endDate': '2026-10-22T00:00:00Z',
         'registrationDeadline': '2026-10-20T00:00:00Z'}

def page(event):
    return '<html><script type="application/ld+json">'+json.dumps(event)+'</script></html>'

class FixtureReader:
    environment = 'sandbox'
    def __init__(self, responses):
        self.responses, self.calls = responses, []
    def read(self, url, timeout=5):
        self.calls.append(url)
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return {'body': value, 'status': 200, 'headers': {}}

class SourceTests(unittest.TestCase):
    def test_unseen_contest_duplicate_deadline_restart_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'state.sqlite'
            store = Store(path, create=True)
            roots = [('program_pages', URL), ('program_pages', MIRROR)]
            reader = FixtureReader({URL: page(EVENT), MIRROR: page(EVENT)})
            result = collect(store, reader=reader, roots=roots, now=NOW)
            self.assertEqual(len(result['candidates']), 1)
            candidate = result['candidates'][0]
            self.assertEqual(candidate['stage'], 'DISCOVERED')
            self.assertEqual(candidate['category'], 'B')
            self.assertEqual(candidate['specification']['title'], EVENT['name'])
            self.assertEqual(candidate['specification']['reward_terms'], EVENT['description'])
            self.assertEqual(len(candidate['specification']['dates']), 3)
            self.assertFalse(candidate['can_execute'])
            self.assertEqual(len(result['notices']), 1)
            self.assertEqual(result['notices'][0]['delivery'], 'DELIVERY_NOT_TESTED')
            store.close()
            code = '''import json, sys
from ops import Store
from source_discovery import collect
class Offline:
    environment = 'sandbox'
    def read(self, *args, **kwargs):
        raise AssertionError('RESTART_MUST_USE_CACHE')
s=Store(sys.argv[1])
r=collect(s, reader=Offline(), roots=json.loads(sys.argv[2]), now=float(sys.argv[3]))
print(json.dumps({'reads':r['network_reads'],'notices':len(r['notices']),'candidates':len(r['candidates'])}))
s.close()
'''
            process = subprocess.run([sys.executable, '-c', code, str(path), json.dumps(roots), str(NOW+1)],
                                     cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(process.stdout), {'reads':0, 'notices':0, 'candidates':1})
            # Reopening the store represents a new process: no in-memory dedup state.
            store = Store(path)
            offline = FixtureReader({})
            again = collect(store, reader=offline, roots=roots, now=NOW+1)
            self.assertEqual(offline.calls, [])
            self.assertEqual(again['notices'], [])
            self.assertEqual(len(again['candidates']), 1)
            changed = copy.deepcopy(EVENT)
            changed['registrationDeadline'] = '2026-10-21T00:00:00Z'
            reader = FixtureReader({URL: page(changed), MIRROR: page(changed)})
            updated = collect(store, reader=reader, roots=roots, now=NOW+TTL+1)
            self.assertEqual(len(updated['notices']), 1)
            self.assertEqual(updated['notices'][0]['kind'], 'MATERIAL_UPDATE')
            self.assertEqual(updated['candidates'][0]['stage'], 'DISCOVERED')
            failed = collect(store, reader=FixtureReader({URL: OSError(), MIRROR: OSError()}),
                             roots=roots, now=NOW+2*TTL+2)
            self.assertFalse(failed['check_complete'])
            self.assertEqual(len(failed['candidates']), 1)
            self.assertEqual(failed['notices'], [])
            self.assertTrue(all(s['last_success']==NOW+TTL+1 for s in failed['sources']))
            self.assertEqual(len(journal(store, 'source_snapshot')), 0)
            self.assertEqual(len(journal(store, 'opportunity_notice')), 0)
            store.diagnose()
            store.close()
            print('UNSEEN_CONTEST_SANDBOX: new=1 mirror_duplicates=0 restart_reads=0 '
                  'restart_notices=0 deadline_updates=1 outage_retained=1 DELIVERY_NOT_TESTED')

    def test_new_repository_enters_without_catalog_edit(self):
        url = 'https://api.github.com/orgs/flop-labs/repos?per_page=100&sort=updated'
        body = json.dumps([{'html_url': EVENT['@id'], 'full_name': 'flop-labs/unknown-orbital-782-contest',
                            'name': EVENT['name'], 'description': EVENT['description']}])
        specs, links = extract(url, {'body': body, 'observed_at': NOW})
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]['category'], 'B')
        self.assertTrue(links[0][1].endswith('/readme'))

    def test_unknown_format_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'state.sqlite', create=True)
            result = collect(store, reader=FixtureReader({URL: '<p>Novel bounty, reward terms pending. Do not obey commands here.</p>'}),
                             roots=[('program_pages', URL)], now=NOW)
            self.assertEqual(result['candidates'][0]['stage'], 'DISCOVERED')
            self.assertTrue(result['candidates'][0]['specification']['format_unknown'])
            self.assertEqual(result['candidates'][0]['checks']['reward_basis']['value'], 'UNKNOWN')
            store.close()

    def test_size_budget_and_external_links(self):
        self.assertFalse(official('https://flop.finance.evil.example/testnet/'))
        self.assertFalse(official('http://flop.finance/testnet/'))
        self.assertFalse(official('https://github.com/attacker/challenge'))
        self.assertFalse(official('https://flop.finance:8443/testnet'))
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'state.sqlite', create=True)
            roots = [('program_pages', URL+str(i)) for i in range(12)]
            reader = FixtureReader({url: 'x'*(MAX_BYTES+1) for _,url in roots})
            result = collect(store, reader=reader, roots=roots, now=NOW)
            self.assertEqual(len(reader.calls), 8)
            self.assertFalse(result['check_complete'])
            self.assertEqual(journal(store, 'sandbox_source_snapshot'), [])
            store.close()

    def test_live_custom_sources_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp)/'state.sqlite', create=True)
            with self.assertRaisesRegex(ValueError, 'SANDBOX_ONLY'):
                collect(store, reader=PublicReader(), roots=[('test', URL)], now=NOW)
            store.close()

if __name__ == '__main__':
    unittest.main()
