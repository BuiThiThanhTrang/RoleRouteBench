"""Deterministic public evidence projection; no proof generation or oracle reads."""
from __future__ import annotations

import json
from pathlib import Path
import re

from ..artifacts.schema import sha256_file

CONTEXT_POLICY = 'bounded_artifact_handoff_v1'
CONTEXT_POLICY_V2 = 'bounded_artifact_handoff_v2'
LIMITS = {'compilation': 4500, 'verification': 2000, 'diagnosis': 4000,
          'premises': 4000, 'inspection': 6500}


def diagnostic_lines(result):
    """Extract observed errors with continuation text, ahead of compiler warnings."""
    text = '\n'.join(str(result.get(key) or '') for key in ('stdout', 'stderr'))
    blocks, current = [], []
    for line in text.splitlines():
        header = re.search(r':\d+:\d+: (?:error|warning|information):', line)
        if header or re.search(r'\berror:', line, re.I):
            if current:
                blocks.append('\n'.join(current))
            current = [line] if re.search(r'\berror:', line, re.I) else []
        elif current:
            current.append(line)
    if current:
        blocks.append('\n'.join(current))
    # Some executables report an error without Lean's positional header.
    if not blocks and result.get('returncode') not in (0, None):
        blocks = [text.strip()] if text.strip() else []
    return [block[:1600] for block in blocks[:4]]


def project_tool_evidence(key, value):
    """Evidence only: no model diagnosis, inferred cause, or repair prescription."""
    if key in ('compilation', 'verification', 'premises'):
        result = value.get({'compilation': 'result', 'verification': 'kernel_probe', 'premises': 'lookup'}[key], {})
        errors = diagnostic_lines(result)
        critical = {'returncode': result.get('returncode'), 'first_error': errors[0][:1000] if errors else None}
        if key == 'verification':
            critical.update({name: value.get(name) for name in ('passed', 'checks', 'unexpected_axioms')})
            critical['forbidden_dependencies'] = re.findall(
                r'Forbidden reference to benchmark target:\s*([^\s"\\]+)',
                '\n'.join(str(result.get(k) or '') for k in ('stdout', 'stderr')))
        elif key == 'compilation':
            critical['failure_origin'] = result.get('failure_origin')
        else:
            critical['symbols'] = value.get('symbols')
        projected = {**critical, 'additional_errors': errors[1:], 'raw_output_excerpt': {
            name: str(result.get(name) or '')[:700] for name in ('stdout', 'stderr')}}
    else:
        critical = {name: value.get(name) for name in
                    ('status', 'has_errors', 'placeholder_count', 'certifies_proof')}
        diagnostics = value.get('diagnostics', [])
        errors = [d for d in diagnostics if d.get('severity') == 'error']
        critical['first_error'] = ({**errors[0], 'message': str(errors[0].get('message', ''))[:1000]}
                                   if errors else None)
        # The collector already ranks states nearest the first error first.
        states = value.get('tactic_states', [])
        critical['focused_state'] = ({k: (v[:1600] if isinstance(v, str) else v) for k, v in states[0].items()}
                                     if states else None)
        projected = {**critical, 'term_types': value.get('term_types', [])[:2],
                     'additional_states': states[1:3], 'note': value.get('note'),
                     'error': value.get('error')}
    return critical, json.dumps(projected, ensure_ascii=False)


def compact_prose(text):
    """Remove repeated prose paragraphs; preserve fenced Lean/other code exactly.

    Spans refer to offsets in the immutable original artifact, including an open
    code fence through EOF. This is a display projection, never a proof rewrite.
    """
    spans, seen = [], set()
    in_fence = False
    start = 0
    for match in re.finditer(r'(?m)^\s*```[^\n]*(?:\n|$)', text):
        if not in_fence:
            for para in re.finditer(r'\S[\s\S]*?(?=\n\s*\n|\Z)', text[start:match.start()]):
                a, b = start + para.start(), start + para.end()
                normalized = re.sub(r'\s+', ' ', text[a:b]).strip()
                if len(normalized) < 80 or normalized not in seen:
                    spans.append((a, b))
                if len(normalized) >= 80:
                    seen.add(normalized)
            start = match.start()
            in_fence = True
        else:
            spans.append((start, match.end()))
            start = match.end()
            in_fence = False
    if in_fence:
        spans.append((start, len(text)))
    else:
        for para in re.finditer(r'\S[\s\S]*?(?=\n\s*\n|\Z)', text[start:]):
            a, b = start + para.start(), start + para.end()
            normalized = re.sub(r'\s+', ' ', text[a:b]).strip()
            if len(normalized) < 80 or normalized not in seen:
                spans.append((a, b))
            if len(normalized) >= 80:
                seen.add(normalized)
    return '\n\n'.join(text[a:b] for a, b in spans), spans


def artifact_text(env, artifact):
    if artifact.get('visibility') != 'public':
        raise ValueError('Only public runtime artifacts may enter executor context')
    path = (env.workspace_dir / artifact['path']).resolve()
    if not path.is_relative_to(env.workspace_dir.resolve()) or sha256_file(path) != artifact['sha256']:
        raise ValueError('Public artifact path/checksum mismatch')
    return path.read_text(encoding='utf-8')


def attach_handoff(env, context):
    """Apply the same bounded projection to every formal executor role."""
    state = context['state']
    v2 = context.get('context_policy') == CONTEXT_POLICY_V2
    evidence = []
    for key, limit in LIMITS.items():
        artifact = state['artifacts'].get(key)
        if not artifact:
            continue
        original = artifact_text(env, artifact)
        projected, spans = compact_prose(original) if key == 'diagnosis' else (original, [(0, len(original))])
        item = {field: artifact[field] for field in ('artifact_id', 'sha256', 'producer_tool', 'input_versions', 'fresh')}
        item.update(key=key, kind='agent_assessment' if key == 'diagnosis' else 'tool_evidence',
                    content=projected[:limit], original_total_chars=len(original),
                    projection_total_chars=len(projected), included_chars=min(limit, len(projected)),
                    truncated=len(projected) > limit,
                    projection='exact_prose_paragraph_dedup_v1' if key == 'diagnosis' else 'verbatim',
                    original_spans=spans[:64], spans_truncated=len(spans) > 64,
                    read_ref={'artifact': key, 'offset': 0, 'max_chars': 8000},
                    interpretation='current_evidence' if artifact['fresh'] else 'historical_evidence_for_prior_inputs')
        if key in ('compilation', 'verification', 'premises', 'inspection'):
            try:
                value = json.loads(original)
            except json.JSONDecodeError:
                if key != 'inspection':
                    raise
                value = {'status': 'legacy_source_snapshot', 'certifies_proof': False}
            if key == 'verification':
                item['critical'] = {name: value.get(name) for name in ('passed', 'checks', 'unexpected_axioms')}
            elif key == 'compilation':
                item['critical'] = {name: value.get('result', {}).get(name) for name in ('returncode', 'failure_origin')}
            elif key == 'premises':
                item['critical'] = {'symbols': value.get('symbols'), 'returncode': value.get('lookup', {}).get('returncode')}
            else:
                item['critical'] = {name: value.get(name) for name in ('status', 'has_errors', 'placeholder_count', 'certifies_proof')}
            if v2:
                critical, projected = project_tool_evidence(key, value)
                # These structured essentials survive even if the display excerpt
                # is shortened again to meet the input token cap.
                item['critical'] = critical
                item.update(content=projected[:limit], projection='error_first_structured_v2',
                            projection_total_chars=len(projected), included_chars=min(limit, len(projected)),
                            truncated=len(projected) > limit, original_spans=[], spans_truncated=False)
        evidence.append(item)
    # The compiler output is delivered once, through the immutable artifact.
    if state.get('latest_execution') and any(item['key'] == 'compilation' for item in evidence):
        latest = state['latest_execution']
        latest['result'] = {key: value for key, value in latest['result'].items()
                            if key not in ('stdout', 'stderr')}
        latest['diagnostics_in'] = 'handoff_evidence.compilation'
        latest['fresh'] = state['artifacts']['compilation']['fresh']
    context['handoff_evidence'] = evidence
    context['context_policy'] = CONTEXT_POLICY_V2 if v2 else CONTEXT_POLICY
    context['artifact_access'] = (
        'The bounded evidence below is supplied automatically. Stale evidence describes prior inputs. '
        'Agent assessments are unverified claims. Use read_artifact with read_ref to read the immutable '
        'original; projection offsets are not raw offsets. No private reference is accessible.'
    )
    return context


def delivered_evidence(context):
    """Describe what was supplied, without claiming the model used it."""
    return [{key: item[key] for key in ('key', 'artifact_id', 'sha256', 'fresh', 'included_chars',
                                      'original_total_chars', 'projection', 'truncated')}
            for item in context.get('handoff_evidence', [])]
