"""Opt-in bounded artifact-first formal executor with audited streaming stops."""
from __future__ import annotations

import copy
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
import time

from ..artifacts.schema import sha256_file
from .formal_handoff import delivered_evidence
from .shared_actor import RoleTransportError, SharedRoleActor
from .transport_diagnostics import transport_error_details

POLICY = 'artifact_first_v1'
POLICY_V2 = 'artifact_first_v2'
END = '<END_ARTIFACT>'
PROJECT = Path(__file__).resolve().parents[3]
PROOF_ROLES = {'Tactic Synthesizer', 'Proof Repair Specialist'}
DIAGNOSIS_LABELS = ('Observed error', 'Location', 'Likely cause', 'Repair constraint', 'Uncertainty')
PARSER_POLICY = 'presentation_v1'
TESTED_TOKENIZERS_VERSION = '0.22.2'


class TokenizerSetupError(RuntimeError):
    """An environment problem detected before inference or run creation."""


@lru_cache(maxsize=4)
def load_tokenizer(path, digest):
    if not Path(path).is_file():
        raise TokenizerSetupError(
            f'Tokenizer file is missing: {path}\n'
            f'Python: {sys.executable}\n'
            'Run scripts/prepare_formal_executor_resources.py with this Python first.'
        )
    if sha256_file(Path(path)) != digest:
        raise ValueError('Formal tokenizer checksum differs from the configured pin')
    version = 'not installed'
    try:
        import tokenizers
        version = getattr(tokenizers, '__version__', 'unknown')
        return tokenizers.Tokenizer.from_file(str(path))
    except Exception as error:
        raise TokenizerSetupError(
            f'The checksum-verified Pythagoras tokenizer could not be loaded.\n'
            f'Python: {sys.executable}\n'
            f'Installed tokenizers: {version}; tested dependency: tokenizers=={TESTED_TOKENIZERS_VERSION}.\n'
            'Use the Python verified for Formal, or a separate Formal environment. '
            'Do not upgrade an older Transformers environment in place if it requires tokenizers<0.20.\n'
            'In the separate Formal environment, install:\n'
            f'  python -m pip install -r "{PROJECT / "requirements-formal-environment.txt"}"\n'
            'Then rerun the audit with --check-only. The pinned tokenizer and token budget have not been changed.'
        ) from error


def repetition(text, *, plain_source=False):
    """Conservative long-prose loops and identical recursively nested open tactics.

    Ordinary repeated identifiers/tactic lines are not a repetition failure.
    No text is rewritten by this detector.
    """
    chunks = re.split(r'(?m)^\s*```[^\n]*(?:\n|$)', text)
    prose = '\n'.join(chunks[::2])[-18000:]
    if text.lstrip().startswith(('by', 'theorem ', 'lemma ')):
        prose = ''
    if plain_source and looks_like_lean_source(text):
        prose = ''
    paragraphs = [re.sub(r'\s+', ' ', part).strip() for part in re.split(r'\n\s*\n', prose)]
    for paragraph, count in Counter(part for part in paragraphs if len(part) >= 80).items():
        if count >= 4 and len(paragraph) * count >= 600:
            return {'kind': 'repeated_prose_paragraph', 'repeat_count': count, 'sample': paragraph[:180]}
    words = re.findall(r'\w+|[^\w\s]', prose)[-1000:]
    for width in range(16, min(161, len(words) // 4 + 1)):
        block = words[-width:]
        if all(words[-width * (n + 1): -width * n] == block for n in range(1, 4)):
            return {'kind': 'repeated_prose_suffix', 'repeat_count': 4, 'period_words': width,
                    'sample': ' '.join(block)[:180]}
    lines = [line for line in text.splitlines()[-60:] if line.strip() and not line.lstrip().startswith('--')]
    if len(lines) >= 12:
        tail = lines[-12:]
        normalized = [line.strip() for line in tail]
        indents = [len(line) - len(line.lstrip()) for line in tail]
        if len(set(normalized)) == 1 and normalized[0].endswith(('(by', ':= by')) and all(
                b > a for a, b in zip(indents, indents[1:])):
            return {'kind': 'recursive_open_tactic', 'repeat_count': 12, 'sample': normalized[0][:180]}
    return None


class ContextBudgetExceeded(ValueError):
    pass


def looks_like_lean_source(text):
    from .adapters.formal_proof import uncomment
    return bool(re.match(r'^\s*(?:by|theorem|lemma|import|open|namespace|section|variable|universe|set_option|noncomputable|def|abbrev)\b',
                         uncomment(text)))


def diagnosis_fields(text, *, partial=False, presentation=False):
    """Keep only finished, bounded labeled lines; never extract plans or Lean."""
    fields = {}
    if '```' in text or '<think>' in text:
        return fields
    lines = text.splitlines(keepends=True)
    for line in lines:
        if partial and not line.endswith(('\n', '\r')):
            continue
        if presentation:
            line = re.sub(r'^\s*(?:(?:\d{1,2}[.)]|[-*+])\s+)?', '', line)
            line = re.sub(r'^\*\*(' + '|'.join(DIAGNOSIS_LABELS) + r')(?::\*\*|\*\*:)[ \t]*',
                          r'\1: ', line, flags=re.I)
        match = re.fullmatch(r'(' + '|'.join(DIAGNOSIS_LABELS) + r'): ([^\r\n]+)\s*', line,
                            flags=re.I if presentation else 0)
        if match and presentation:
            label = next(label for label in DIAGNOSIS_LABELS if label.casefold() == match[1].casefold())
            value = match[2].strip()
            if label in fields and fields[label] != value:
                return {}  # Conflicting assessments must not be silently resolved.
            if 0 < len(value) <= 450:
                fields[label] = value
            continue
        if match and match[1] not in fields and 0 < len(match[2].strip()) <= 450:
            fields[match[1]] = match[2].strip()
    return fields


class FormalRoleActor(SharedRoleActor):
    def __init__(self, *args, formal_protocol, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol = dict(formal_protocol)
        if self.protocol.get('version') not in (POLICY, POLICY_V2):
            raise ValueError('Unknown formal executor protocol')
        path = Path(self.protocol['tokenizer_path'])
        path = path if path.is_absolute() else PROJECT / path
        self.tokenizer = load_tokenizer(str(path.resolve()), self.protocol['tokenizer_sha256'])
        self.action = None
        self.policy = self.protocol['version']
        if self.protocol.get('parser_policy') not in (None, PARSER_POLICY):
            raise ValueError('Unknown formal parser policy')
        if self.protocol.get('parser_policy') and self.policy != POLICY_V2:
            raise ValueError('Presentation parser requires artifact_first_v2')
        self._generation_requests = []
        generation = self.protocol.get('generation', {})
        for settings in [generation, *self.protocol.get('role_generation', {}).values()]:
            if set(settings) - {'temperature', 'top_p', 'enable_thinking'}:
                raise ValueError('Unknown formal generation option')
            for key, high in [('temperature', 2), ('top_p', 1)]:
                if key in settings and (isinstance(settings[key], bool) or not isinstance(settings[key], (int, float))
                                        or not 0 <= settings[key] <= high or (key == 'top_p' and settings[key] == 0)):
                    raise ValueError(f'Invalid formal generation {key}')
            if 'enable_thinking' in settings and not isinstance(settings['enable_thinking'], bool):
                raise ValueError('enable_thinking must be a boolean')
        unknown_roles = set(self.protocol.get('role_generation', {})) - (PROOF_ROLES | {
            'Formal Failure Diagnostician', 'Premise and Lemma Retriever'})
        if unknown_roles:
            raise ValueError('Generation settings supplied for unknown/non-LLM roles')
        self.ceiling = self.max_tokens
        for name, default in [('proof_max_tokens', 4096), ('diagnosis_max_tokens', 1024), ('retrieval_max_tokens', 1024)]:
            value = self.protocol.get(name, default)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value > self.ceiling:
                raise ValueError(f'Invalid {name}')

    def execute(self, **kwargs):
        self.action = kwargs['action']
        self._generation_requests = []
        adapter, env = kwargs['adapter'], kwargs['env']
        before = adapter.public_observation(env) if self.policy == POLICY_V2 else None
        self.max_tokens = min(self.ceiling, self.protocol.get(
            'proof_max_tokens' if self.action in PROOF_ROLES else
            'diagnosis_max_tokens' if self.action == 'Formal Failure Diagnostician' else 'retrieval_max_tokens',
            4096 if self.action in PROOF_ROLES else 1024))
        try:
            result = super().execute(**kwargs)
            for index, request in enumerate(result.get('requests', [])):
                request.update(stream=True, stream_options={'include_usage': True}, executor_protocol=self.policy)
                if index < len(self._generation_requests):
                    request.update(self._generation_requests[index])
                payload = request.get('executor_payload', {})
                request['delivered_evidence'] = delivered_evidence(payload.get('public_context', {}))
            if self.policy == POLICY_V2:
                error = result.get('contract_error')
                if error and result.get('responses'):
                    meta = result['responses'][-1]['metadata']
                    details = meta.get('generation_details')
                    if error.get('code') == 'stream_interrupted' and isinstance(details, dict):
                        # Provider body/IDs are audit-only. Keep the pre-existing
                        # feedback visible to the router and following actors.
                        details = {key: details.get(key) for key in ('error_type', 'http_status')}
                    error.update(generation_details=details,
                                 observed_completion_tokens=meta.get('observed_completion_tokens'))
            if result.get('contract_error', {}).get('code') == 'stream_interrupted':
                result.update(status='transport_error', failure_origin='executor_service')
            if result.get('contract_error', {}).get('code') == 'context_budget_exceeded':
                result.update(status='tool_failure', failure_origin='tool_environment')
            if self.policy == POLICY_V2:
                adapter.record_role_result(env, self.action, before, result)
            return result
        except ContextBudgetExceeded as error:
            return {'status': 'tool_failure', 'failure_origin': 'tool_environment', 'raw_output': '', 'responses': [], 'requests': [], 'tool_events': [],
                    'contract_error': {'role': self.action, 'code': 'context_budget_exceeded', 'message': str(error)}}
        finally:
            self.max_tokens = self.ceiling

    def instruction_for(self, instruction, *, action, adapter, plain_tool):
        if self.policy == POLICY_V2 and plain_tool == 'write_diagnosis':
            return (
                'Return exactly five short labeled lines. One or two sentences per line, at most 450 characters per field. '
                'Use unknown when the evidence does not establish a cause. The observed error must come from supplied '
                'tool evidence. Compilation success and verifier rejection are different outcomes. '
                'No proof, code, abstract plan, task restatement, or next-role choice.\n'
                'Format example (illustrative, not evidence about this task):\n'
                'Observed error: unknown constant Example.missingLemma\n'
                'Location: line 8, column 4\n'
                'Likely cause: the submitted name is unavailable in the pinned environment.\n'
                'Repair constraint: preserve the statement and replace or avoid that reference.\n'
                'Uncertainty: the correct replacement has not been checked.\n'
                f'End with {END} on a separate line. '
                'If essential evidence is missing, you may instead return the allowed JSON read_artifact request.'
            )
        if self.policy == POLICY_V2 and action == 'Premise and Lemma Retriever':
            return (instruction + ' Return only the allowed JSON tool call, with 1–8 Lean symbol names for write_premises. '
                    'No proof, plan, or prose. Do not propose a forbidden original target. '
                    'The tool checks names in the pinned environment; do not claim they were checked already.')
        if plain_tool == 'write_source':
            if self.protocol.get('parser_policy') == PARSER_POLICY:
                return (
                    'Produce one complete Lean proof artifact: a proof term beginning with by, '
                    'the original theorem declaration with its proof, or the original full source with its proof. '
                    'Each form is accepted as plain Lean or inside one Lean code fence. '
                    'Preserve every immutable context/statement token; the harness retains the original context. '
                    'No analysis, plan, skeleton, duplicate versions, or commentary. Never submit sorry/admit. '
                    f'After the proof emit {END} on its own line and stop. '
                    'If essential evidence is missing, return the allowed JSON read_artifact request instead. '
                    'Do not choose the next role.'
                )
            return (
                'Produce the artifact first: ONLY one Lean proof term beginning with by, or one Lean code fence '
                'containing that proof term. No analysis, plan, skeleton, duplicate versions, or commentary. '
                'Use the immutable source context and the supplied current evidence. Never submit sorry/admit. '
                f'After the proof emit {END} on its own line and stop. '
                'If more evidence is essential, instead return one JSON read_artifact request using the allowed schema. '
                'Do not choose the next role.'
            )
        if plain_tool == 'write_diagnosis':
            return (
                'Return a concise handoff with exactly these labeled sections: Observed failure; Location; '
                'Suspected cause; Repair constraints; Uncertainty. Ground claims in supplied tool evidence. '
                'Do not write a proof, repeat the task, invent facts, or choose the next role. '
                f'Finish with {END} on its own line. '
                'If evidence is missing, return one JSON read_artifact request instead.'
            )
        return instruction

    def render_payload(self, payload, adapter):
        # Render evidence verbatim, as for Lean source, instead of nesting a
        # serialized JSON artifact inside another JSON string in the prompt.
        display = copy.deepcopy(payload)
        sections = []
        for item in display['public_context'].get('handoff_evidence', []):
            content = item.pop('content')
            item['content_rendering'] = 'Verbatim public artifact section below'
            sections.append(f"\n\nPUBLIC ARTIFACT {item['key']} | {item['artifact_id']} | fresh={item['fresh']} | {item['kind']}\n{content}\nEND PUBLIC ARTIFACT")
        rendered = super().render_payload(display, adapter)
        metadata, separator, source = rendered.partition('\n\nCURRENT LEAN SOURCE\n')
        return metadata + ''.join(sections) + separator + source

    def prepare_payload(self, payload, *, adapter, instruction):
        payload = copy.deepcopy(payload)
        context = payload['public_context']
        cap = int(self.protocol.get('input_max_tokens', 8192))
        def size():
            text = 'You are a bounded executor in a multi-agent workflow.\n' + instruction + '\n' + self.render_payload(payload, adapter)
            return len(self.tokenizer.encode(text, add_special_tokens=False).ids) + 512
        while size() > cap:
            items = [item for item in context.get('handoff_evidence', []) if len(item['content']) > 512]
            if items:
                item = max(items, key=lambda item: (len(item['content']), item['key']))
                item['content'] = item['content'][:max(512, len(item['content']) // 2)]
                item['included_chars'], item['truncated'] = len(item['content']), True
                continue
            source = context['state'].get('source', '')
            if len(source) > 2000:
                source = source[:max(2000, len(source) // 2)]
                context['state']['source'] = source
                context['state']['source_access']['visible_chars'] = len(source)
                continue
            raise ContextBudgetExceeded('Required context exceeds the configured input budget after bounded previews')
        context['input_budget'] = {'policy': self.policy, 'max_tokens': cap,
                                   'estimated_tokens_with_chat_reserve': size(), 'chat_reserve_tokens': 512}
        return payload

    def prepare_work_product(self, raw, metadata):
        if metadata.get('diagnosis_artifact'):
            return json.dumps(metadata['diagnosis_artifact'], ensure_ascii=False)
        return raw[:metadata.get('artifact_end_offset', len(raw))].strip()

    def generation_options(self):
        settings = {**self.protocol.get('generation', {}),
                    **self.protocol.get('role_generation', {}).get(self.action, {})}
        options = {'temperature': settings.get('temperature', 0)}
        if 'top_p' in settings:
            options['top_p'] = settings['top_p']
        if 'enable_thinking' in settings:
            options['extra_body'] = {'chat_template_kwargs': {'enable_thinking': settings['enable_thinking']}}
        return options

    def _query(self, messages):
        request_tokens = len(self.tokenizer.encode('\n'.join(message['content'] for message in messages), add_special_tokens=False).ids) + 256
        if request_tokens > self.protocol.get('input_max_tokens', 8192):
            return '', {'generation_error': 'context_budget_exceeded', 'error_message': 'Read-expanded context exceeds the input budget',
                        'finish_reason': 'context_budget_exceeded', 'request_sent': False, 'usage': None}
        options = self.generation_options()
        self._generation_requests.append(copy.deepcopy(options))
        for attempt in range(self.transport_retries + 1):
            started = time.perf_counter()
            parts, usage, model, generation_id, provider_finish = [], None, None, None, None
            stream, error, details, end_at = None, None, None, None
            normalization = None
            diagnosis = None
            last_check = 0
            try:
                stream = self.client.chat.completions.create(model=self.model, messages=messages,
                    max_tokens=self.max_tokens, stream=True, stream_options={'include_usage': True}, **options)
                for chunk in stream:
                    model = getattr(chunk, 'model', None) or model
                    generation_id = getattr(chunk, 'id', None) or generation_id
                    chunk_usage = getattr(chunk, 'usage', None)
                    if chunk_usage is not None:
                        usage = chunk_usage.model_dump()
                    for choice in chunk.choices or []:
                        provider_finish = choice.finish_reason or provider_finish
                        delta = getattr(choice.delta, 'content', None)
                        if delta:
                            parts.append(delta)
                    text = ''.join(parts)
                    boundary = re.search(r'(?m)^' + re.escape(END) + r'\r?$', text)
                    if boundary:
                        end_at = boundary.start()
                        break
                    if len(text) - last_check >= 128 or ('\n' in (parts[-1] if parts else '')):
                        last_check = len(text)
                        details = repetition(text, plain_source=self.protocol.get('parser_policy') == PARSER_POLICY)
                        if details:
                            error = 'repetition_detected'
                            break
                text = ''.join(parts)
                details = details or repetition(text, plain_source=self.protocol.get('parser_policy') == PARSER_POLICY)
                if details:
                    error = 'repetition_detected'
                elif provider_finish == 'length':
                    error = 'output_truncated'
                elif provider_finish != 'stop' and end_at is None:
                    error = 'generation_incomplete'
                if self.policy == POLICY_V2 and self.action == 'Formal Failure Diagnostician':
                    product = text[:end_at] if end_at is not None else text
                    fields = diagnosis_fields(product, partial=bool(error),
                                              presentation=self.protocol.get('parser_policy') == PARSER_POLICY)
                    if error in ('output_truncated', 'repetition_detected') and all(k in fields for k in DIAGNOSIS_LABELS[:2]):
                        diagnosis = {'status': 'partial', 'fields': fields, 'unverified_assessment': True,
                                     'generation_failure': error}
                        error = None
                    elif not error:
                        try:
                            reading = json.loads(product).get('tool') == 'read_artifact'
                        except (ValueError, AttributeError):
                            reading = False
                        if len(fields) == len(DIAGNOSIS_LABELS):
                            diagnosis = {'status': 'complete', 'fields': fields, 'unverified_assessment': True}
                        elif not reading:
                            error = 'diagnosis_format'
                if self.action in PROOF_ROLES and not error:
                    product = text[:end_at].strip() if end_at is not None else text.strip()
                    read_request = False
                    try:
                        read_request = json.loads(product).get('tool') == 'read_artifact'
                    except (ValueError, AttributeError):
                        pass
                    plain = re.match(r'^(?:by|theorem|lemma)\b', product) is not None and '```' not in product
                    if self.protocol.get('parser_policy') == PARSER_POLICY and '```' not in product:
                        # Forward source-shaped text to the existing adapter. Its
                        # immutable context/statement and command checks remain
                        # authoritative; never recover a proof by deleting Lean.
                        plain = looks_like_lean_source(product)
                        if plain:
                            normalization = {'strategy': 'plain_lean_to_existing_immutable_adapter_v1',
                                             'lean_content_rewritten': False}
                    blocks = re.findall(r'```(?:lean4?)?\s*\n(.*?)```', product, re.S)
                    fenced = bool(blocks) and product.count('```') % 2 == 0
                    if fenced:
                        normalization = {'strategy': 'existing_adapter_last_complete_lean_block',
                                         'complete_lean_blocks': len(blocks), 'selected_lean_block': len(blocks) - 1,
                                         'selected_without_compiling_alternatives': True}
                    if not (read_request or plain or fenced):
                        error = 'artifact_format'
            except Exception as exception:
                if parts:
                    text = ''.join(parts)
                    error = 'stream_interrupted'
                    details = transport_error_details(exception, response=getattr(stream, 'response', None))
                else:
                    status = getattr(exception, 'status_code', None)
                    if attempt >= self.transport_retries or status not in (None, 408, 409, 429, 500, 502, 503, 504):
                        raise RoleTransportError(exception) from None
                    time.sleep(min(2 ** (attempt + 1), 30))
                    continue
            finally:
                if stream is not None:
                    stream.close()
            metadata = {'model': model, 'generation_id': generation_id, 'usage': usage,
                        'finish_reason': error or ('artifact_end' if end_at is not None else provider_finish),
                        'provider_finish_reason': provider_finish, 'transport_attempt': attempt,
                        'latency_ms': int((time.perf_counter() - started) * 1000),
                        'executor_protocol': self.policy, 'max_tokens': self.max_tokens,
                        'generation_options': options,
                        'thinking_requested': options.get('extra_body', {}).get('chat_template_kwargs', {}).get('enable_thinking'),
                        'thinking_application': 'provider_requested_not_independently_verified',
                        'observed_completion_tokens': len(self.tokenizer.encode(text, add_special_tokens=False).ids),
                        'usage_available': usage is not None, 'stream_closed_early': end_at is not None or error == 'repetition_detected'}
            if end_at is not None:
                metadata['artifact_end_offset'] = end_at
            if normalization is not None:
                metadata['output_normalization'] = normalization
            if diagnosis is not None:
                metadata['diagnosis_artifact'] = diagnosis
                if diagnosis['status'] == 'partial':
                    metadata['finish_reason'] = 'partial_diagnosis'
                    metadata['generation_failure'] = diagnosis['generation_failure']
                    metadata['stream_closed_early'] = diagnosis['generation_failure'] == 'repetition_detected'
            if error:
                metadata.update(generation_error=error, error_message='No work product was submitted: ' + error,
                                generation_details=details)
            return text, metadata
