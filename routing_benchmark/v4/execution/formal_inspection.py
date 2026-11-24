"""Collect real tactic/term states without modifying or certifying a proof."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time

from ..artifacts.schema import sha256_file
from .adapters.common import read_json, write_json
from .adapters.formal_proof import uncomment

DRIVER = Path(__file__).parent / 'lean/InspectProof.lean'
INSPECTION_POLICY = 'tactic_state_v1'
MARKER = 'FORMAL_INSPECTION_JSON:'


def select_states(rows, errors, count):
    """Prefer the narrowest source span containing the first actual error."""
    if not errors:
        return rows[-count:]
    point = (errors[0]['line'], errors[0]['column'])
    def rank(row):
        p = row['position']
        start, end = (p['line'], p['column']), (p['end_line'], p['end_column'])
        contains = start <= point <= end
        return (not contains, (end[0] - start[0]) * 10000 + end[1] - start[1]
                if contains else abs(start[0] - point[0]) * 10000 + abs(start[1] - point[1]))
    return sorted(rows, key=rank)[:count]


def inspect_candidate(env, runtime):
    source = env.workspace_dir / 'public/Main.lean'
    source_hash = sha256_file(source)
    driver_hash = sha256_file(DRIVER)
    key = {'source_sha256': source_hash, 'driver_sha256': driver_hash,
           'lean_executable': runtime.get('lean_executable'), 'lean_path': runtime.get('lean_path'),
           'runtime_profile': runtime.get('project_dir')}
    cache = env.workspace_dir / '_runtime/tactic_inspection_cache.json'
    if cache.exists():
        previous = read_json(cache)
        if previous.get('cache_key') == key:
            return {**previous['report'], 'cache_hit': True}, previous.get('trace')
    text = source.read_text(encoding='utf-8')
    masked = uncomment(text)
    placeholders = []
    for match in re.finditer(r'\b(?:sorry|admit)\b', masked):
        placeholders.append({'line': text.count('\n', 0, match.start()) + 1,
                             'column': match.start() - text.rfind('\n', 0, match.start())})
    report = {'policy': INSPECTION_POLICY, 'source_sha256': source_hash,
              'collector_sha256': driver_hash, 'status': 'unavailable', 'certifies_proof': False,
              'placeholder_count': len(placeholders), 'placeholder_locations': placeholders,
              'position_convention': '1-based line and Unicode codepoint column',
              'cache_hit': False}
    trace = None
    if not runtime.get('lean_executable') or not runtime.get('project_dir'):
        return {**report, 'error': 'Pinned Lean runtime is not configured'}, trace
    environment = dict(os.environ)
    if runtime.get('lean_path'):
        environment['LEAN_PATH'] = runtime['lean_path']
    started = time.perf_counter()
    try:
        result = subprocess.run([runtime['lean_executable'], '--run', str(DRIVER), str(source.resolve())],
                                cwd=runtime['project_dir'], env=environment, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=180,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        report['collector_exit_code'] = result.returncode
        report['elapsed_ms'] = int((time.perf_counter() - started) * 1000)
        outputs = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
        if result.returncode != 0 or not outputs:
            return {**report, 'error': 'Lean inspection collector failed',
                    'collector_stdout': result.stdout[:4000], 'collector_stderr': result.stderr[:2000]}, trace
        trace = json.loads(outputs[-1])
        diagnostics = trace['diagnostics']
        errors = [item for item in diagnostics if item['severity'] == 'error']
        states = select_states(trace['tactic_states'], errors, 10)
        types = select_states(trace['term_types'], errors, 8)
        report.update(status='partial' if trace['has_errors'] or trace['tactics_capped'] or trace['terms_capped'] else 'complete',
                      has_errors=trace['has_errors'], diagnostics=diagnostics[:30],
                      diagnostics_truncated=len(diagnostics) > 30,
                      tactic_states=states, term_types=types,
                      captured_tactics=len(trace['tactic_states']), captured_terms=len(trace['term_types']),
                      tactic_states_capped=trace['tactics_capped'], term_types_capped=trace['terms_capped'],
                      note='Goals and local context are Lean observations. Zero goals or successful elaboration does not certify a proof; placeholders and kernel assumptions require verification.')
        if not states:
            report['goal_availability'] = 'No tactic state was available; consult diagnostics/term types and the declared initial goal.'
    except subprocess.TimeoutExpired:
        return {**report, 'error': 'Inspection timed out', 'timeout_seconds': 180}, trace
    except (OSError, ValueError, KeyError) as error:
        return {**report, 'error': str(error)}, trace
    if sha256_file(source) != source_hash:
        raise ValueError('Candidate changed during inspection')
    write_json(cache, {'cache_key': key, 'report': report, 'trace': trace})
    return report, trace
