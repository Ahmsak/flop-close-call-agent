"""Synthetic public HTTP responses only; never calls the gateway."""
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

import agent
import flop_gateway as gateway
from ops import NoRedirect, Store


class Response(io.BytesIO):
    def __init__(self, body, status=200, url=gateway.MODELS_URL, content_type='application/json'):
        super().__init__(body)
        self.status, self.url = status, url
        self.headers = Message()
        self.headers['Content-Type'] = content_type

    def geturl(self):
        return self.url


VALID = {'object': 'list', 'data': [{'object': 'model', 'id': 'fixture/model',
          'created': 1, 'owned_by': 'fixture', 'x-flop': {'untrusted': 'not evidence'}}],
         'total_count': 1, 'links': {'next': None}}


class GatewayTests(unittest.TestCase):
    def invoke(self, value=VALID, *, response=None, error=None, **kwargs):
        opener = Mock()
        opener.open.side_effect = error
        opener.open.return_value = response if response is not None else Response(json.dumps(value).encode())
        with patch('flop_gateway.urllib.request.build_opener', return_value=opener) as build:
            result = gateway.discover_models(**kwargs)
        return result, opener, build

    def test_success_fixed_get_no_secrets_or_proxy(self):
        with patch.dict('os.environ', {'FLOP_API_KEY': 'secret', 'HTTPS_PROXY': 'https://secret@invalid'}):
            result, opener, build = self.invoke()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, gateway.MODELS_URL)
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(set(k.lower() for k in request.headers), {'accept', 'accept-encoding', 'user-agent'})
        self.assertEqual(opener.open.call_args.kwargs['timeout'], gateway.TIMEOUT)
        self.assertEqual(opener.open.call_count, 1)
        self.assertIs(build.call_args.args[0], NoRedirect)
        self.assertEqual(build.call_args.args[1].proxies, {})
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(result['models'], [{'id': 'fixture/model', 'object': 'model'}])
        self.assertFalse(result['testnet_ready'])
        self.assertFalse(result['network_identity_verified'])
        self.assertEqual(result['inference_available'], 'UNKNOWN')
        self.assertNotIn('untrusted', json.dumps(result))
        self.assertNotIn('secret', json.dumps(result))

    def test_no_write_or_custom_endpoint_interface(self):
        for key, value in [('method', 'POST'), ('method', 'PUT'), ('method', 'PATCH'),
                           ('method', 'DELETE'), ('url', 'https://invalid'),
                           ('headers', {'Authorization': 'secret'}), ('body', {}),
                           ('did', 'fixture'), ('private_key', 'secret'), ('wallet', {})]:
            with self.subTest(key=key, value=value), patch('urllib.request.build_opener') as build:
                with self.assertRaises(TypeError):
                    gateway.discover_models(**{key: value})
                build.assert_not_called()

    def test_testnet_and_unknown_profile_no_network(self):
        for network in ['testnet', 'mainnet']:
            result, opener, build = self.invoke(network=network)
            build.assert_not_called()
            opener.open.assert_not_called()
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertEqual(result['request_attempts'], 0)
            self.assertFalse(result['testnet_ready'])

    def test_http_errors_sanitized_no_retries(self):
        for status, reason in [(403, 'HTTP_FORBIDDEN'), (429, 'HTTP_RATE_LIMITED'),
                               (500, 'HTTP_SERVER_ERROR'), (503, 'HTTP_SERVER_ERROR'),
                               (401, 'HTTP_ERROR'), (404, 'HTTP_ERROR')]:
            with self.subTest(status=status):
                body = io.BytesIO(b'private error content')
                error = urllib.error.HTTPError(gateway.MODELS_URL, status, 'secret',
                                               {'Retry-After': '1'}, body)
                result, opener, _ = self.invoke(error=error)
                self.assertEqual(result['reason'], reason)
                self.assertEqual(result['http_status'], status)
                self.assertEqual(opener.open.call_count, 1)
                self.assertTrue(body.closed)
                self.assertNotIn('secret', json.dumps(result))

    def test_redirects_never_followed(self):
        for status in [301, 302, 303, 307, 308]:
            result, opener, _ = self.invoke(error=urllib.error.HTTPError(
                gateway.MODELS_URL, status, '', {'Location': 'https://invalid/private'}, None))
            self.assertEqual(result['reason'], 'REDIRECT_BLOCKED')
            self.assertEqual(opener.open.call_count, 1)
            self.assertIsNone(NoRedirect().redirect_request(None, None, status, '', {}, 'https://invalid'))
        result, _, _ = self.invoke(response=Response(b'{}', url='https://invalid'))
        self.assertEqual(result['reason'], 'REDIRECT_BLOCKED')

    def test_network_timeout_tls_and_disconnect(self):
        for error, reason in [(TimeoutError('secret'), 'NETWORK_TIMEOUT'),
                              (urllib.error.URLError(TimeoutError()), 'NETWORK_TIMEOUT'),
                              (urllib.error.URLError('secret'), 'NETWORK_UNAVAILABLE'),
                              (OSError('secret'), 'NETWORK_UNAVAILABLE'),
                              (gateway.http.client.IncompleteRead(b'secret'), 'NETWORK_UNAVAILABLE')]:
            result, opener, _ = self.invoke(error=error)
            self.assertEqual(result['reason'], reason)
            self.assertEqual(opener.open.call_count, 1)
            self.assertNotIn('secret', json.dumps(result))

    def test_invalid_json_duplicate_keys_and_nonfinite(self):
        for body in [b'<html>', b'\xff', b'{"object":"list","object":"list"}', b'{"data":NaN}']:
            result, _, _ = self.invoke(response=Response(body))
            self.assertEqual(result['reason'], 'JSON_INVALID')

    def test_schema_rejects_incomplete_contradictory_types(self):
        for value in [None, [], {}, {'object': 'list', 'data': {}},
                      {'object': 'list', 'data': [{'id': 'x'}]},
                      {**VALID, 'data': [VALID['data'][0]] * 2},
                      {**VALID, 'total_count': True}, {**VALID, 'total_count': 0},
                      {**VALID, 'links': {'next': 1}},
                      {**VALID, 'data': [{'object': 'model', 'id': 'bad\nID'}]},
                      {**VALID, 'data': [{'object': 'model', 'id': 'x', 'created': True}]}]:
            with self.subTest(value=value):
                result, _, _ = self.invoke(value)
                self.assertEqual(result['reason'], 'MODEL_SCHEMA_INVALID')

    def test_size_and_content_type_encoding_limits(self):
        response = Response(b'x' * (gateway.MAX_BYTES + 2))
        result, _, _ = self.invoke(response=response)
        self.assertEqual(result['reason'], 'RESPONSE_TOO_LARGE')
        self.assertTrue(response.closed)
        result, _, _ = self.invoke(response=Response(b'{}', content_type='text/html'))
        self.assertEqual(result['reason'], 'CONTENT_TYPE_INVALID')
        response = Response(b'{}'); response.headers['Content-Encoding'] = 'gzip'
        result, _, _ = self.invoke(response=response)
        self.assertEqual(result['reason'], 'CONTENT_ENCODING_UNSUPPORTED')

    def test_empty_and_partial_listing_do_not_claim_market_coverage(self):
        result, _, _ = self.invoke({'object': 'list', 'data': []})
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(result['models'], [])
        result, opener, _ = self.invoke({**VALID, 'links': {'next': 'https://invalid'}})
        self.assertEqual(result['coverage'], 'PARTIAL')
        self.assertFalse(result['pagination_followed'])
        self.assertEqual(opener.open.call_count, 1)

    def test_existing_journal_reopen_retains_evidence_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'fixture.sqlite'
            store = Store(path, create=True)
            result, _, _ = self.invoke(store=store)
            store.close()
            store = Store(path)
            try:
                self.assertEqual(store.diagnose()['events_verified'], 1)
                row = store.db.execute('SELECT kind,evidence FROM events').fetchone()
                self.assertEqual(row['kind'], 'gateway_model_discovery')
                self.assertEqual(json.loads(row['evidence']), result)
                self.assertEqual(store.db.execute('SELECT count(*) FROM operations').fetchone()[0], 0)
            finally:
                store.close()

    def test_cli_defaults_do_not_load_config_or_store(self):
        output = io.StringIO()
        with patch('sys.argv', ['agent.py', 'gateway-models']), patch('ops.Store') as store, \
                patch('pathlib.Path.read_text', side_effect=AssertionError('private config')), \
                patch('flop_gateway.discover_models', return_value={'status': 'OK'}) as discover, \
                contextlib.redirect_stdout(output):
            agent.main()
        store.assert_not_called()
        discover.assert_called_once_with(network='devnet', store=None)
        self.assertEqual(json.loads(output.getvalue())['status'], 'OK')

    def test_cli_blocked_profile_exit_two_without_network(self):
        with patch('sys.argv', ['agent.py', 'gateway-models', '--gateway-network', 'testnet']), \
                patch('urllib.request.build_opener') as build, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                agent.main()
        self.assertEqual(error.exception.code, 2)
        build.assert_not_called()

    def test_cli_explicit_missing_journal_fails_before_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'absent.sqlite'
            with patch('sys.argv', ['agent.py', 'gateway-models', '--gateway-journal', str(path)]), \
                    patch('flop_gateway.discover_models') as discover, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    agent.main()
            discover.assert_not_called()
            self.assertFalse(path.exists())
