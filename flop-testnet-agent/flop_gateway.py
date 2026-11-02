"""Public model discovery only; no inference, signing, account or wallet interface.

Endpoint/profile reference: https://docs.flop.network/docs/sdk-references
The validated discovery subset is not receipt, pricing or chain verification.
"""
import hashlib
import http.client
import socket
import time
import urllib.error
import urllib.request

from ops import NoRedirect, strict_json

MODELS_URL = 'https://api.flop.network/v1/models'
TIMEOUT = 8
MAX_BYTES = 512 * 1024
MAX_MODELS = 1000


def _models(value):
    if not isinstance(value, dict) or value.get('object') != 'list':
        raise ValueError('MODEL_SCHEMA_INVALID')
    rows = value.get('data')
    if not isinstance(rows, list) or len(rows) > MAX_MODELS:
        raise ValueError('MODEL_SCHEMA_INVALID')
    models, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or row.get('object') != 'model':
            raise ValueError('MODEL_SCHEMA_INVALID')
        key = row.get('id')
        if (not isinstance(key, str) or not 1 <= len(key) <= 256
                or any(ord(c) < 33 or ord(c) == 127 for c in key) or key in seen):
            raise ValueError('MODEL_SCHEMA_INVALID')
        if 'created' in row and (type(row['created']) is not int or row['created'] < 0):
            raise ValueError('MODEL_SCHEMA_INVALID')
        if 'owned_by' in row and (not isinstance(row['owned_by'], str) or len(row['owned_by']) > 256):
            raise ValueError('MODEL_SCHEMA_INVALID')
        seen.add(key)
        # Do not propagate arbitrary extensions, prices, links or supposed receipts.
        models.append({'id': key, 'object': 'model'})
    total = value.get('total_count', len(rows))
    if type(total) is not int or total < len(rows):
        raise ValueError('MODEL_SCHEMA_INVALID')
    links = value.get('links', {})
    if not isinstance(links, dict):
        raise ValueError('MODEL_SCHEMA_INVALID')
    next_page = links.get('next')
    if next_page is not None and (not isinstance(next_page, str) or not next_page or len(next_page) > 2048):
        raise ValueError('MODEL_SCHEMA_INVALID')
    return models, total, next_page is not None or total > len(rows)


def discover_models(*, network='devnet', store=None):
    """One fixed unauthenticated GET. Optional existing Store journal, never init.

    Timeout is a socket-operation timeout, not a total wall-clock SLA (DNS and
    slow streaming can take longer). No retries, proxy credentials or redirects.
    Testnet is deliberately unavailable until its separate profile is verified.
    """
    result = {'source': MODELS_URL, 'observed_at': time.time(),
              'network_profile': network, 'network_identity_verified': False,
              'testnet_ready': False, 'inference_available': 'UNKNOWN',
              'execution': 'EXECUTION_DISABLED', 'http_status': None,
              'request_attempts': 0, 'models': [], 'status': 'ERROR',
              'timeout_seconds': TIMEOUT, 'max_bytes': MAX_BYTES,
              'automatic_retries': 0}
    if network != 'devnet':
        result.update(status='BLOCKED', reason='NETWORK_PROFILE_NOT_VERIFIED')
    else:
        # No caller URL, body, headers, credentials, method or signing parameters.
        request = urllib.request.Request(MODELS_URL, method='GET', headers={
            'Accept': 'application/json', 'Accept-Encoding': 'identity',
            'User-Agent': 'FLOP-Agent/model-discovery'})
        opener = urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler({}))
        result['request_attempts'] = 1
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                result['http_status'] = response.status
                if response.geturl() != MODELS_URL or 300 <= response.status < 400:
                    raise ValueError('REDIRECT_BLOCKED')
                if response.status != 200:
                    raise urllib.error.HTTPError(MODELS_URL, response.status, '', {}, None)
                if response.headers.get_content_type() != 'application/json':
                    raise ValueError('CONTENT_TYPE_INVALID')
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise ValueError('CONTENT_ENCODING_UNSUPPORTED')
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError('RESPONSE_TOO_LARGE')
                result['response_sha256'] = hashlib.sha256(raw).hexdigest()
                try:
                    value = strict_json(raw.decode('utf-8'))
                except (ValueError, UnicodeError, RecursionError):
                    raise ValueError('JSON_INVALID') from None
                models, total, partial = _models(value)
                result.update(status='OK', models=models, total_count=total,
                              coverage='PARTIAL' if partial else 'RETURNED_PAGE',
                              pages_read=1, pagination_followed=False)
        except urllib.error.HTTPError as error:
            code = error.code
            result['http_status'] = code
            result['reason'] = ('REDIRECT_BLOCKED' if 300 <= code < 400 else
                                'HTTP_FORBIDDEN' if code == 403 else
                                'HTTP_RATE_LIMITED' if code == 429 else
                                'HTTP_SERVER_ERROR' if 500 <= code < 600 else 'HTTP_ERROR')
            error.close()  # Never read/log error bodies, Location or auth headers.
        except (TimeoutError, socket.timeout):
            result['reason'] = 'NETWORK_TIMEOUT'
        except urllib.error.URLError as error:
            result['reason'] = ('NETWORK_TIMEOUT' if isinstance(error.reason, TimeoutError)
                                else 'NETWORK_UNAVAILABLE')
        except (OSError, http.client.HTTPException):
            result['reason'] = 'NETWORK_UNAVAILABLE'
        except ValueError as error:
            # All validation errors above use fixed local codes, not remote text.
            result['reason'] = str(error)
    if store is not None:
        store.record('', 'gateway_model_discovery', result)
    return result
