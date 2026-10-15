"""Isolated Technocore-shaped HTTP fixture and synthetic job/reward convention."""
import base64
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ops import B58, Operator, Store, Technocore, canonical, digest, strict_json, verify_record
from jobs import choose, discover, solve

class TestIdentity:
    """Ephemeral SANDBOX identity. Never reads the owner's key or config."""
    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        raw = b'\xed\x01' + self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        number, encoded = int.from_bytes(raw, 'big'), ''
        while number:
            number, remainder = divmod(number, 58)
            encoded = B58[remainder] + encoded
        self.did, self.nonce = 'did:key:z' + encoded, 0

    def envelope(self, room, text):
        self.nonce += 1
        sig = base64.urlsafe_b64encode(self.key.sign(f'{room}|{self.nonce}|{text}'.encode())).decode().rstrip('=')
        return {'did': self.did, 'nonce': self.nonce, 'text': text, 'sig': sig}

class Venue:
    def __init__(self):
        self.rows, self.posts, self.generation = {}, 0, 1
        self.drop_reply, self.fail_reads, self.hide_records = False, False, False
        venue = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, body):
                raw = canonical(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                room = urlsplit(self.path).path.removeprefix('/r/')
                if venue.fail_reads:
                    self.respond(503, {'error': 'source down'})
                    return
                rows = [] if venue.hide_records else venue.rows.get(room, [])
                self.respond(200, {'room': room, 'generation': venue.generation, 'messages': rows[-200:],
                                   'first_seq': rows[0]['seq'] if rows else 0, 'last_seq': len(rows)})

            def do_POST(self):
                room = urlsplit(self.path).path.removeprefix('/r/')
                body = strict_json(self.rfile.read(int(self.headers['Content-Length'])))
                try:
                    row = venue.append(room, body)
                except Exception:
                    self.respond(400, {'error': 'invalid signature'})
                    return
                venue.posts += 1
                if venue.drop_reply:
                    venue.drop_reply = False
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.respond(200, row)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def append(self, room, envelope):
        row = {**envelope, 'from': envelope['did']}
        row.pop('did')
        verify_record(room, row)
        rows = self.rows.setdefault(room, [])
        row.update(seq=len(rows)+1, ts=time.time())
        rows.append(row)
        return row

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

def grant_for(operator, operation):
    request = strict_json(operator.store.get(operation)['request'])
    return {'environment': 'sandbox', 'request_hash': digest(request), 'origin': operator.transport.origin,
            'room': request['room'], 'did': request['body']['did'], 'max_writes': 1,
            'max_spend': '0', 'expires_at': time.time()+120}

def demo(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    db_path = directory/'state.sqlite'
    owner, requester = TestIdentity(), TestIdentity()
    with Venue() as venue:
        transport = Technocore(venue.origin, sandbox=True)
        store = Store(db_path, create=True)
        now = time.time()
        job = {'kind': 'local-job-v1', 'id': 'invoice-001', 'created_at': now, 'deadline': now+180,
               'workload': 'invoice_totals_v1', 'input': 'sku,quantity,unit_price\nA,2,3.50\nB,1,4\nA,1,2\n',
               'reward': '10', 'unit': 'PAPER', 'max_cost': '0'}
        venue.append('jobs', requester.envelope('jobs', canonical(job)))
        found = discover(transport, store, room='jobs', requester=requester.did)
        task, strategy = choose(found['eligible'])
        result = solve(task)
        submission = {'kind': 'local-job-result-v1', 'job': task['id'], 'result': result}
        operator = Operator(store, transport, owner.did)
        operation = operator.prepare(task['id'], 'delivery', owner.envelope('delivery', canonical(submission)),
                                     valid_until=task['deadline'], source_seen_at=task['source_seen_at'])
        grant = grant_for(operator, operation)
        venue.drop_reply = True
        first = operator.execute(operation, grant)
        store.close()
        # A separate process must reconcile the retained record without a write grant.
        resumed_process = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), 'resume', str(db_path.resolve()),
             venue.origin, owner.did, operation], capture_output=True, text=True, encoding='utf-8', timeout=15)
        if resumed_process.returncode:
            raise RuntimeError('resume process failed: '+resumed_process.stderr)
        resumed = strict_json(resumed_process.stdout)
        store = Store(db_path)
        operator = Operator(store, transport, owner.did)
        received = strict_json(venue.rows['delivery'][0]['text'])
        if received['result'] != {'A': '9.00', 'B': '4'}:
            raise AssertionError('requester rejected wrong result')
        acceptance = {'kind': 'local-job-accepted-v1', 'operation': operation,
                      'result_hash': digest(received['result']), 'reward': '10', 'unit': 'PAPER'}
        venue.append('delivery', requester.envelope('delivery', canonical(acceptance)))
        reward = operator.reward(operation, requester.did)
        report = {'environment': 'LOCAL_SANDBOX', 'scenario': 'data job over Technocore HTTP',
                  'discovered': len(found['eligible']), 'strategy': strategy, 'result': result,
                  'after_lost_response': first['state'], 'after_restart': resumed['state'],
                  'resumed_in_separate_process': True,
                  'post_count': venue.posts, 'reward_status': reward['status'],
                  'paper_reward': reward.get('paper_reward'), 'money_received': '0',
                  'events_verified': store.diagnose()['events_verified'], 'operation': operation,
                  'database': str(db_path.resolve()), 'external_writes': 0}
        store.backup(directory/'state.backup.sqlite')
        store.close()
        (directory/'run.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report

if __name__ == '__main__':
    if len(sys.argv) != 6 or sys.argv[1] != 'resume':
        raise SystemExit('Only sandbox resume is supported here')
    state = Store(sys.argv[2])
    try:
        runner = Operator(state, Technocore(sys.argv[3], sandbox=True), sys.argv[4])
        print(json.dumps(runner.execute(sys.argv[5]), ensure_ascii=True))
    finally:
        state.close()
