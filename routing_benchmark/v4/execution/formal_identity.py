"""Conservative presentation identity, never a proof or freshness certificate."""
from __future__ import annotations

from bisect import bisect_right
import hashlib
import json
import re

IDENTITY_POLICY = 'lean_tokens_layout_v1'
DELIMITERS = '()[]{},⟨⟩⟪⟫'


def source_identity(source):
    """Ignore comments/blank lines/inline spacing; retain literals and layout.

    This deliberately keeps token-line boundaries and first-token columns: Lean
    indentation can change meaning. Unsupported/unclosed literals/comments fall
    back to exact source identity. No source is rewritten or compiled here.
    """
    tokens, i, valid = [], 0, True
    size = len(source)
    while i < size:
        if source[i].isspace():
            i += 1
            continue
        if source.startswith('--', i):
            end = source.find('\n', i)
            i = size if end < 0 else end
            continue
        if source.startswith('/-', i):
            depth, i = 1, i + 2
            while i < size and depth:
                if source.startswith('/-', i):
                    depth, i = depth + 1, i + 2
                elif source.startswith('-/', i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            if depth:
                valid = False
                break
            continue
        start = i
        raw = re.match(r'r(#+)?"', source[i:])
        if raw:
            closing = '"' + (raw[1] or '')
            end = source.find(closing, i + raw.end())
            if end < 0:
                valid = False
                break
            i = end + len(closing)
        elif source[i] == '"':
            i += 1
            while i < size:
                if source[i] == '\\':
                    i += 2
                elif source[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            else:
                valid = False
                break
        elif source[i] == '«':
            end = source.find('»', i + 1)
            if end < 0:
                valid = False
                break
            i = end + 1
        elif source[i] == "'" and (char := re.match(r"'(?:\\[^\r\n]+?|[^\\'\r\n])'", source[i:])):
            i += char.end()
        elif name := re.match(r"\w[\w']*(?:\.\w[\w']*)*", source[i:]):
            i += name.end()
        elif source[i] in DELIMITERS:
            i += 1
        else:
            i += 1
            while i < size and source[i] not in DELIMITERS and not source[i].isspace() and not re.match(r"[\w\"'«]", source[i]):
                if source.startswith(('--', '/-'), i):
                    break
                i += 1
        tokens.append((start, source[start:i]))
    if not valid:
        payload = ['exact_source_fallback', source]
    else:
        starts = [0] + [m.end() for m in re.finditer('\n', source)]
        lines, previous = [], None
        for offset, token in tokens:
            line = bisect_right(starts, offset) - 1
            if line != previous:
                column = len(source[starts[line]:offset].expandtabs(8))
                lines.append([column, []])
                previous = line
            lines[-1][1].append(token)
        payload = lines
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    return {'policy': IDENTITY_POLICY, 'fingerprint': digest, 'lexed': valid,
            'interpretation': 'Presentation identity only; exact-source compilation and verification are still required.'}
