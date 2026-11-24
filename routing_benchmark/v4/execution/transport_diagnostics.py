"""Bounded, credential-redacted provider errors for audit logs only."""
from __future__ import annotations

import json
import os
import re

BODY_LIMIT = 8192
ID_HEADERS = ('x-request-id', 'request-id', 'x-correlation-id', 'x-amzn-requestid', 'cf-ray')


def _attribute(value, name):
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def _redact(text, error):
    secrets = [value for name, value in os.environ.items() if len(value) >= 8 and
               re.search(r'(?:^|_)(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD)(?:_|$)', name, re.I)]
    request = _attribute(error, 'request')
    headers = _attribute(request, 'headers')
    if headers is not None:
        for name in ('authorization', 'api-key', 'x-api-key'):
            value = headers.get(name)
            if value:
                secrets.append(str(value))
                if str(value).lower().startswith('bearer '):
                    secrets.append(str(value)[7:])
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\b(?:hf_[A-Za-z0-9]+|sk-[A-Za-z0-9_-]+)\b', '[REDACTED]', text)
    # Providers may echo credentials that are not present in this process's env.
    text = re.sub(
        r'''(?ix)(["']?(?:authorization|(?:x[-_])?api[-_]?key|access[-_]?token|refresh[-_]?token|password|client[-_]?secret)["']?\s*[:=]\s*)
        (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;<>&]+)''',
        lambda match: match[1] + '"[REDACTED]"', text)
    return text


def transport_error_details(error, *, response=None):
    """Keep response body/trace IDs, never request headers or request payloads.

    Error diagnostics must also work for connection errors and unreadable HTTP
    responses. Missing fields remain null rather than dumping exception reprs.
    """
    original_response = _attribute(error, 'response')
    response = original_response if original_response is not None else response
    headers = _attribute(response, 'headers')
    ids = {}
    if headers is not None:
        for name in ID_HEADERS:
            value = headers.get(name)
            if value:
                ids[name] = _redact(str(value), error)[:256]
    body = _attribute(error, 'body')
    if body is None:
        body = _attribute(response, 'text')
    request_id = _attribute(error, 'request_id')
    if request_id is None and isinstance(body, dict):
        nested = body.get('error')
        for value in (body, nested if isinstance(nested, dict) else {}):
            request_id = value.get('request_id') or value.get('requestId')
            if request_id:
                break
    request_id = request_id or next(iter(ids.values()), None)
    if body is not None:
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)
        text = _redact(text, error)
    else:
        text = None
    return {
        'error_type': type(error).__name__,
        'http_status': _attribute(error, 'status_code'),
        'request_id': _redact(str(request_id), error)[:256] if request_id else None,
        'provider_request_ids': ids,
        'error_body': text[:BODY_LIMIT] if text is not None else None,
        'error_body_truncated': text is not None and len(text) > BODY_LIMIT,
    }
