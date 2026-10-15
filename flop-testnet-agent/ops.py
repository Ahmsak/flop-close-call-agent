"""Durable single-agent operations. No LLM or private-key custody required."""
import base64
import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def verify_record(room, row):
    did = row['from']
    if not re.fullmatch(r'did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}', did):
        raise ValueError('unsupported DID')
    number = 0
    for char in did[9:]:
        number = number * 58 + B58.index(char)
    key = number.to_bytes(34, 'big')
    if key[:2] != b'\xed\x01' or not re.fullmatch(r'[A-Za-z0-9_-]{85}[AQgw]', row['sig']):
        raise ValueError('invalid key/signature encoding')
    if type(row['nonce']) is not int or not 0 <= row['nonce'] < 10**19:
        raise ValueError('invalid nonce')
    message = f"{room}|{row['nonce']}|{row['text']}".encode()
    Ed25519PublicKey.from_public_bytes(key[2:]).verify(base64.urlsafe_b64decode(row['sig']+'=='), message)
    return did

class Store:
    def __init__(self, path, *, create=False):
        self.path = Path(path)
        if not create and not self.path.is_file():
            raise RuntimeError('STATE_MISSING: restore the existing database; do not resend')
        if create and self.path.exists():
            raise RuntimeError('state already exists')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA synchronous=FULL')
        if create:
            self.db.executescript('''
                CREATE TABLE operations(id TEXT PRIMARY KEY, job TEXT UNIQUE, request TEXT,
                    state TEXT, generation INTEGER, receipt TEXT, reward TEXT);
                CREATE TABLE events(seq INTEGER PRIMARY KEY, at REAL, operation TEXT,
                    kind TEXT, evidence TEXT, previous TEXT, hash TEXT);
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO metadata VALUES('schema','1');
            ''')
        if self.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('STATE_CORRUPT')

    def close(self):
        self.db.close()

    def event(self, operation, kind, evidence):
        previous = self.db.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        previous = previous[0] if previous else ''
        at = time.time()
        payload = canonical(evidence)
        checksum = digest([at, operation, kind, payload, previous])
        self.db.execute('INSERT INTO events(at,operation,kind,evidence,previous,hash) VALUES(?,?,?,?,?,?)',
                        (at, operation, kind, payload, previous, checksum))

    def record(self, operation, kind, evidence):
        with self.db:
            self.event(operation, kind, evidence)

    def get(self, operation):
        row = self.db.execute('SELECT * FROM operations WHERE id=?', (operation,)).fetchone()
        if row is None:
            raise ValueError('unknown operation')
        return dict(row)

    def diagnose(self):
        previous = ''
        count = 0
        for row in self.db.execute('SELECT * FROM events ORDER BY seq'):
            if row['previous'] != previous or row['hash'] != digest([
                    row['at'], row['operation'], row['kind'], row['evidence'], previous]):
                raise RuntimeError('EVIDENCE_CORRUPT')
            previous = row['hash']
            count += 1
        return {'sqlite': self.db.execute('PRAGMA integrity_check').fetchone()[0],
                'events_verified': count, 'operations': [dict(row) for row in
                self.db.execute('SELECT id,job,state,reward FROM operations')],
                'llm_required': False}

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise ValueError('backup destination already exists')
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class Technocore:
    """Only documented read-room and POST-room routes; no GET mutation routes."""
    def __init__(self, origin='https://technocore.chat', *, sandbox=False, timeout=8):
        parsed = urlsplit(origin)
        local = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
        if (sandbox and not local) or (not sandbox and origin != 'https://technocore.chat'):
            raise ValueError('origin not allowed for this environment')
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('origin must not contain path or credentials')
        self.origin, self.sandbox, self.timeout = origin, sandbox, timeout
        self.opener = urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler({}))

    def room(self, room):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,47}', room):
            raise ValueError('invalid room')
        return self.origin + '/r/' + room

    def request(self, url, body=None):
        request = urllib.request.Request(url, data=None if body is None else canonical(body).encode(),
                                         headers={'Content-Type': 'application/json', 'User-Agent': 'FLOP-Agent/2'})
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('response size exceeded')
            return strict_json(raw)

    def read(self, room):
        result = self.request(self.room(room) + '?format=json&limit=200')
        if result.get('room') != room or type(result.get('generation')) is not int:
            raise ValueError('invalid room response')
        if not isinstance(result.get('messages'), list):
            raise ValueError('invalid messages')
        return result

    def publish(self, request, grant, now):
        authorize(request, grant, self, now)
        return self.request(self.room(request['room']), request['body'])

def authorize(request, grant, transport, now):
    # Owner-controlled local grant, not network-provided data. One exact operation.
    if grant is None:
        raise PermissionError('EXECUTION_DISABLED: owner grant required')
    expected_environment = 'sandbox' if transport.sandbox else 'live'
    if (grant.get('environment') != expected_environment or grant.get('request_hash') != digest(request)
            or grant.get('origin') != transport.origin or grant.get('room') != request['room']
            or grant.get('did') != request['body']['did'] or grant.get('max_writes') != 1
            or grant.get('max_spend') != '0' or not now < grant.get('expires_at', 0)):
        raise PermissionError('EXECUTION_DISABLED: grant scope, budget or expiry mismatch')
    if request['origin'] != transport.origin:
        raise PermissionError('origin mismatch')

class Operator:
    def __init__(self, store, transport, owner_did, *, clock=time.time):
        self.store, self.transport, self.owner_did, self.clock = store, transport, owner_did, clock
        binding = canonical({'origin': transport.origin, 'did': owner_did, 'sandbox': transport.sandbox})
        with store.db:
            old = store.db.execute("SELECT value FROM metadata WHERE key='binding'").fetchone()
            if old and old[0] != binding:
                raise ValueError('STATE_IDENTITY_OR_ENVIRONMENT_MISMATCH')
            if not old:
                store.db.execute("INSERT INTO metadata VALUES('binding',?)", (binding,))

    def prepare(self, job, room, envelope, *, valid_until, source_seen_at):
        now = self.clock()
        if not 0 <= now - source_seen_at <= 300 or valid_until <= now:
            raise ValueError('STALE_OPPORTUNITY')
        if envelope['did'] != self.owner_did or set(envelope) != {'did', 'sig', 'nonce', 'text'}:
            raise ValueError('identity or envelope mismatch')
        text = envelope['text']
        import unicodedata
        if not text or len(text) > 4096 or text != text.strip() or any(
                unicodedata.category(c) in ('Cc', 'Cf', 'Cs', 'Co', 'Zl', 'Zp') for c in text):
            raise ValueError('text would be changed by server sanitation')
        verify_record(room, {**envelope, 'from': envelope['did']})
        request = {'origin': self.transport.origin, 'room': room, 'body': envelope,
                   'valid_until': valid_until, 'source_seen_at': source_seen_at}
        operation = digest(request)
        baseline = self.transport.read(room)
        with self.store.db:
            old = self.store.db.execute('SELECT id FROM operations WHERE job=?', (job,)).fetchone()
            if old:
                if old[0] != operation:
                    raise ValueError('job already prepared with different action')
                return old[0]
            self.store.db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?)',
                                 (operation, job, canonical(request), 'PREPARED', baseline['generation'], None, None))
            self.store.event(operation, 'prepared', {'request': request, 'baseline': baseline})
        return operation

    def execute(self, operation, grant=None):
        self.store.diagnose()
        row = self.store.get(operation)
        request = strict_json(row['request'])
        if digest(request) != operation:
            raise RuntimeError('REQUEST_CORRUPT')
        if row['state'] != 'PREPARED':
            return self.verify(operation)
        authorize(request, grant, self.transport, self.clock())
        if request['valid_until'] <= self.clock() or not 0 <= self.clock()-request['source_seen_at'] <= 300:
            raise ValueError('STALE_OPPORTUNITY')
        # Reconcile BEFORE first send as well. A matching retained record is enough to avoid a duplicate.
        if self.verify(operation)['state'] != 'PREPARED':
            return self.store.get(operation)
        with self.store.db:
            changed = self.store.db.execute("UPDATE operations SET state='SENDING' WHERE id=? AND state='PREPARED'",
                                            (operation,)).rowcount
            if not changed:
                return self.store.get(operation)
            self.store.event(operation, 'send_started', {'request_hash': operation, 'grant': grant})
        try:
            response = self.transport.publish(request, grant, self.clock())
        except Exception as error:
            with self.store.db:
                self.store.db.execute("UPDATE operations SET state='UNKNOWN' WHERE id=?", (operation,))
                self.store.event(operation, 'send_uncertain', {'error': type(error).__name__})
            return self.store.get(operation)
        with self.store.db:
            self.store.db.execute("UPDATE operations SET state='UNKNOWN' WHERE id=?", (operation,))
            self.store.event(operation, 'http_response', response)
        return self.verify(operation)

    def verify(self, operation):
        row = self.store.get(operation)
        if row['state'] in ('CONFIRMED', 'ACCEPTED'):
            return row
        request = strict_json(row['request'])
        try:
            result = self.transport.read(request['room'])
        except Exception as error:
            self.store.record(operation, 'reconcile_unavailable', {'error': type(error).__name__})
            # Before first send, an unavailable source must stop execution.
            if row['state'] == 'PREPARED':
                raise RuntimeError('SOURCE_UNAVAILABLE') from error
            return row
        match = None
        if result['generation'] == row['generation']:
            for candidate in result['messages']:
                body = request['body']
                if all(candidate.get(k) == body[v] for k, v in
                       (('from','did'), ('text','text'), ('nonce','nonce'), ('sig','sig'))):
                    verify_record(request['room'], candidate)
                    match = candidate
                    break
        with self.store.db:
            self.store.event(operation, 'reconcile', result)
            if match:
                self.store.db.execute("UPDATE operations SET state='CONFIRMED',receipt=? WHERE id=?",
                                      (canonical(match), operation))
            elif row['state'] != 'PREPARED':
                self.store.db.execute("UPDATE operations SET state='UNKNOWN' WHERE id=?", (operation,))
            elif result['generation'] != row['generation']:
                raise RuntimeError('ROOM_GENERATION_CHANGED')
        return self.store.get(operation)

    def reward(self, operation, requester):
        row = self.verify(operation)
        if row['state'] not in ('CONFIRMED', 'ACCEPTED'):
            return {'status': 'UNKNOWN', 'money_received': '0'}
        request = strict_json(row['request'])
        outcome = {'status': 'UNKNOWN', 'money_received': '0'}
        try:
            messages = self.transport.read(request['room'])
        except Exception as error:
            self.store.record(operation, 'reward_unavailable', {'error': type(error).__name__})
            return outcome
        # This is our sandbox job convention, NOT a FLOP/TCLK settlement protocol.
        if self.transport.sandbox and messages['generation'] == row['generation']:
            for record in messages['messages']:
                if record.get('from') != requester:
                    continue
                try:
                    verify_record(request['room'], record)
                    body = strict_json(record['text'])
                    if (body.get('kind') == 'local-job-accepted-v1' and body.get('operation') == operation
                            and body.get('result_hash') == digest(strict_json(request['body']['text'])['result'])):
                        from agent import amount
                        quantity = amount(body['reward'])
                        if body.get('unit') != 'PAPER':
                            continue
                        outcome = {'status': 'SANDBOX_ACCEPTED', 'paper_reward': str(quantity),
                                   'unit': 'PAPER', 'money_received': '0', 'receipt': record}
                except (ValueError, KeyError, TypeError, InvalidSignature):
                    continue
        with self.store.db:
            self.store.event(operation, 'reward_checked', {'room': messages, 'outcome': outcome})
            self.store.db.execute('UPDATE operations SET reward=? WHERE id=?', (canonical(outcome), operation))
            if outcome['status'] == 'SANDBOX_ACCEPTED':
                self.store.db.execute("UPDATE operations SET state='ACCEPTED' WHERE id=?", (operation,))
        return outcome
