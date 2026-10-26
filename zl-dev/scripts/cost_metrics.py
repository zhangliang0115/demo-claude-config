#!/usr/bin/env python3
"""Summarize observed Claude stream-json metrics offline; never execute recorded tools."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys

MAX_LINE_BYTES = 16 * 1024 * 1024
COMMANDS = {
    'reviewable.py': {'init', 'update', 'render', 'continue', 'handoff', 'index', 'verify', 'locate', 'status', 'fingerprint'},
    'feature.py': {'init', 'inspect', 'preflight', 'update', 'sync', 'render', 'locate', 'status'},
    'session_context.py': {'resolve', 'bind', 'clear'},
    'workspace.py': {'inspect', 'status', 'begin', 'end'},
    'analysis.py': {'source'},
}
NOTICE = ('Observed bytes are not tokens, disk IO, network traffic or the complete model context. '
          'Tool syntax does not prove execution, success or business coverage. Result usage is not '
          'summed with assistant usage, modelUsage or model_usage_since_last_result. '
          'modelUsage and total_cost_usd may be session-cumulative on resume; reported cost is not a bill. '
          'trace_state describes parse completeness, never whether the task succeeded.')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def content_bytes(value):
    if value is None:
        return None
    return len((value if isinstance(value, str) else canonical(value)).encode('utf-8'))


def classify_bash(command):
    """Classify only plain argv; shell control, wrappers and dynamic expansion stay ambiguous."""
    if not isinstance(command, str) or not command.strip():
        return {'classification': 'ambiguous', 'reason': 'missing_command'}
    # Expansion inside double quotes is still executable shell code. Conservative
    # classification also rejects literal dollar/backtick characters in single quotes.
    if any(x in command for x in ('\n', '\r', '$', '`', '#', '*', '?', '[', ']', '{', '}', '~')):
        return {'classification': 'ambiguous', 'reason': 'shell_expansion_comment_or_multiline'}
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>()')
        lexer.whitespace_split = True
        lexer.commenters = ''
        argv = list(lexer)
    except ValueError:
        return {'classification': 'ambiguous', 'reason': 'invalid_shell_quoting'}
    if any(re.fullmatch(r'[;&|<>()]+', item) for item in argv):
        return {'classification': 'ambiguous', 'reason': 'shell_control_or_redirection'}
    if not argv:
        return {'classification': 'ambiguous', 'reason': 'missing_command'}
    program = Path(argv[0]).name
    if program in {'env', 'rtk', 'sh', 'bash', 'zsh', 'sudo', 'time', 'timeout', 'command', 'cd'} or '=' in argv[0]:
        return {'classification': 'ambiguous', 'reason': 'wrapper_or_environment'}
    if not re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', program):
        return {'classification': 'other_simple', 'reason': 'not_a_direct_python_plugin_invocation'}
    if len(argv) < 3 or argv[1].startswith('-'):
        return {'classification': 'ambiguous', 'reason': 'python_flags_or_missing_script_action'}
    script, action = Path(argv[1]).name, argv[2]
    if script not in COMMANDS or action not in COMMANDS[script]:
        return {'classification': 'other_simple', 'reason': 'unrecognized_script_action'}
    result = {'classification': 'plugin_invocation_syntax', 'script': script, 'action': action}
    if script == 'reviewable.py' and action in {'continue', 'init'}:
        result['no_render_flag'] = '--no-render' in argv[3:]
    return result


def _collection(value, names=False):
    if not isinstance(value, (list, dict)):
        return {'count': None, 'sha256': None}
    result = {'count': len(value), 'sha256': hashlib.sha256(canonical(value).encode()).hexdigest()}
    if names:
        items = list(value) if isinstance(value, dict) else value
        labels = [x if isinstance(x, str) else x.get('name') if isinstance(x, dict) else None for x in items]
        result['names'] = [x for x in labels[:32] if isinstance(x, str)]
        result['names_truncated'] = len(labels) > 32
    return result


def _init_summary(event):
    return {
        'model': event.get('model'), 'claude_code_version': event.get('claude_code_version'),
        'permission_mode': event.get('permissionMode'),
        'plugins': _collection(event.get('plugins'), names=True),
        'tools': _collection(event.get('tools'), names=True),
        'mcp_servers': _collection(event.get('mcp_servers'), names=True),
        'memory_paths': _collection(event.get('memory_paths')),
        'additional_directories': _collection(event.get('additional_directories')),
        'skills': _collection(event.get('skills')),
        'agents': _collection(event.get('agents')),
        'slash_commands': _collection(event.get('slash_commands')),
    }


def _json_kind(content):
    if not isinstance(content, str) or not content.lstrip().startswith(('{', '[')):
        return None
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        return None
    if isinstance(value, dict) and value.get('version') == 1 and value.get('id') and value.get('title'):
        if isinstance(value.get('project_path'), str) and isinstance(value.get('kind'), str):
            return 'task_record_candidate'
        if all(isinstance(value.get(k), list) for k in ('projects', 'contracts', 'allocations')):
            return 'feature_record_candidate'
    return 'other_json'


def summarize(path, max_line_bytes=MAX_LINE_BYTES):
    """Parse a local log without reading any file named by a tool request."""
    if type(max_line_bytes) is not int or max_line_bytes < 1:
        raise ValueError('max_line_bytes must be a positive integer')
    path = Path(path)
    anomalies = []
    counts = Counter()
    calls, conflicted_calls, results_by_tool, conflicted_results = {}, set(), {}, set()
    final_results, inits = [], []
    raw_hash = hashlib.sha256()

    def anomaly(kind, line=None, **extra):
        counts['anomaly_count'] += 1
        if len(anomalies) < 40:
            anomalies.append(dict(kind=kind, **({'line': line} if line is not None else {}), **extra))

    with path.open('rb') as stream:
        line_number = 0
        while True:
            raw = stream.readline(max_line_bytes + 1)
            if not raw:
                break
            line_number += 1
            counts['line_count'] += 1
            counts['input_bytes'] += len(raw)
            raw_hash.update(raw)
            if len(raw) > max_line_bytes:
                while not raw.endswith(b'\n'):
                    raw = stream.readline(max_line_bytes + 1)
                    if not raw:
                        break
                    raw_hash.update(raw); counts['input_bytes'] += len(raw)
                counts['oversized_lines'] += 1; anomaly('oversized_line', line_number)
                continue
            if not raw.strip():
                continue
            try:
                event = json.loads(raw.decode('utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                if not isinstance(event, dict):
                    raise ValueError('event is not an object')
            except (ValueError, UnicodeError):
                counts['malformed_lines'] += 1; anomaly('invalid_json_event', line_number)
                continue
            counts['parsed_events'] += 1
            kind = event.get('type')
            if kind == 'result':
                final_results.append(event)
            if kind == 'system' and event.get('subtype') == 'init':
                inits.append(_init_summary(event))
            message = event.get('message', {})
            blocks = message.get('content', []) if isinstance(message, dict) else []
            if not isinstance(blocks, list):
                continue
            tool_results = [b for b in blocks if isinstance(b, dict) and b.get('type') == 'tool_result']
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if kind == 'assistant' and block.get('type') == 'tool_use':
                    counts['tool_use_blocks'] += 1
                    identity = block.get('id')
                    if not isinstance(identity, str) or not identity:
                        counts['unidentified_tool_calls'] += 1; anomaly('missing_tool_call_id', line_number)
                        continue
                    record = dict(name=block.get('name'), input=block.get('input'), nested=event.get('parent_tool_use_id') is not None)
                    if identity in calls:
                        counts['repeated_tool_call_blocks'] += 1
                        if canonical(calls[identity]) != canonical(record):
                            conflicted_calls.add(identity); anomaly('conflicting_tool_call_id', line_number)
                    else:
                        calls[identity] = record
                if kind == 'user' and block.get('type') == 'tool_result':
                    counts['tool_result_blocks'] += 1
                    identity = block.get('tool_use_id')
                    if not isinstance(identity, str) or not identity:
                        counts['unidentified_tool_results'] += 1; anomaly('missing_tool_result_id', line_number)
                        continue
                    meta = event.get('tool_use_result') if len(tool_results) == 1 else None
                    file = meta.get('file') if isinstance(meta, dict) and isinstance(meta.get('file'), dict) else None
                    record = dict(content=block.get('content'), is_error=block.get('is_error'), read_file=file)
                    if identity in results_by_tool:
                        counts['repeated_tool_result_blocks'] += 1
                        if canonical(results_by_tool[identity]) != canonical(record):
                            conflicted_results.add(identity); anomaly('conflicting_tool_result_id', line_number)
                    else:
                        results_by_tool[identity] = record

    if not inits:
        anomaly('missing_init_event')
    missing_receipts = sum(identity not in results_by_tool or identity in conflicted_results
                           for identity in calls if identity not in conflicted_calls)
    orphan_results = sum(identity not in calls for identity in results_by_tool)
    if missing_receipts:
        anomaly('tool_calls_missing_receipt', count=missing_receipts)
    if orphan_results:
        anomaly('tool_results_without_observed_call', count=orphan_results)
    if len(final_results) > 1:
        anomaly('multiple_result_events')
    if len(inits) > 1:
        anomaly('multiple_init_events')
    final = final_results[0] if len(final_results) == 1 else None
    reported = None
    if final is not None:
        reported = {key: final.get(key) for key in (
            'subtype', 'is_error', 'num_turns', 'duration_ms', 'duration_api_ms',
            'usage', 'modelUsage', 'model_usage_since_last_result', 'total_cost_usd')}
        denials = final.get('permission_denials')
        reported['permission_denials_count'] = len(denials) if isinstance(denials, list) else None
    tool_counts, bash_counts, invocation_counts = Counter(), Counter(), Counter()
    reads, writes = [], []
    read_bytes_known = write_bytes_known = result_bytes_known = bash_command_bytes = 0
    input_bytes_by_tool = Counter()
    unknown_tool_input_sizes = 0
    json_write_bytes = Counter()
    missing_result_content = 0
    eligible = {identity: call for identity, call in calls.items() if identity not in conflicted_calls}
    for identity, call in eligible.items():
        name = call['name'] if isinstance(call['name'], str) else 'unknown'
        tool_counts[name] += 1
        input_size = content_bytes(call['input'])
        if input_size is None:
            unknown_tool_input_sizes += 1
        else:
            input_bytes_by_tool[name] += input_size
        if call['nested']:
            counts['nested_tool_calls'] += 1
        data = call['input'] if isinstance(call['input'], dict) else {}
        receipt = results_by_tool.get(identity) if identity not in conflicted_results else None
        if name == 'Read':
            file = receipt.get('read_file') if receipt else None
            size = content_bytes(file.get('content')) if file else None
            if size is not None:
                read_bytes_known += size
            reads.append(dict(path=data.get('file_path'), requested_offset=data.get('offset'),
                              requested_limit=data.get('limit'), reported_content_utf8_bytes=size,
                              reported_num_lines=file.get('numLines') if file else None,
                              reported_total_lines=file.get('totalLines') if file else None,
                              reported_start_line=file.get('startLine') if file else None))
        elif name == 'Write':
            size = content_bytes(data.get('content'))
            if size is not None:
                write_bytes_known += size
            candidate = _json_kind(data.get('content'))
            if candidate and size is not None:
                json_write_bytes[candidate] += size
            writes.append(dict(path=data.get('file_path'), input_content_utf8_bytes=size,
                               json_shape=candidate, success_inferred=False))
        elif name == 'Bash':
            command_size = content_bytes(data.get('command'))
            if command_size is not None:
                bash_command_bytes += command_size
            classified = classify_bash(data.get('command'))
            bash_counts[classified['classification']] += 1
            if classified['classification'] == 'plugin_invocation_syntax':
                label = classified['script'] + ':' + classified['action']
                if 'no_render_flag' in classified:
                    label += ':no_render' if classified['no_render_flag'] else ':render_flag_not_deferred'
                invocation_counts[label] += 1
    for identity, receipt in results_by_tool.items():
        if identity in conflicted_results:
            continue
        size = content_bytes(receipt['content'])
        if size is None:
            missing_result_content += 1
        else:
            result_bytes_known += size
    paired_receipts = [results_by_tool[identity] for identity in eligible
                       if identity in results_by_tool and identity not in conflicted_results]
    observed_errors = sum(receipt['is_error'] is True for receipt in paired_receipts)
    unknown_error_flags = missing_receipts + sum(type(receipt['is_error']) is not bool for receipt in paired_receipts)
    complete = not counts['anomaly_count'] and len(final_results) == 1
    return dict(
        version=1, trace_state='complete' if complete else 'partial_or_ambiguous',
        source=dict(path=str(path), sha256=raw_hash.hexdigest(), bytes=counts['input_bytes']),
        parsed_events=counts['parsed_events'], line_count=counts['line_count'],
        result_event_count=len(final_results), reported=reported,
        observed_trace_coverage=dict(init_observed=len(inits) == 1, result_observed=len(final_results) == 1,
                                     identified_call_count=len(calls), missing_receipts=missing_receipts,
                                     orphan_results=orphan_results,
                                     paired_unambiguous_calls=sum(identity in results_by_tool and identity not in conflicted_results
                                         for identity in calls if identity not in conflicted_calls)),
        reporting_scopes={
            'reported.usage': 'result_window_reported_not_summed_with_assistant_messages',
            'reported.modelUsage': 'session_reported_may_be_cumulative',
            'reported.model_usage_since_last_result': 'result_delta_as_reported_not_added_to_usage',
            'reported.total_cost_usd': 'session_reported_may_be_cumulative_not_a_bill',
            'reported.duration_ms': 'result_reported_elapsed_not_measured_tool_time'},
        initialization=inits[0] if len(inits) == 1 else None,
        tools=dict(tool_use_blocks=counts['tool_use_blocks'], unique_identified_tool_calls=len(calls),
                   unambiguous_identified_tool_calls=len(eligible), by_name=dict(tool_counts),
                   repeated_call_blocks=counts['repeated_tool_call_blocks'], conflicting_call_ids=len(conflicted_calls),
                   unidentified_call_blocks=counts['unidentified_tool_calls'], nested_call_count=counts['nested_tool_calls'],
                   tool_result_blocks=counts['tool_result_blocks'], conflicting_result_ids=len(conflicted_results),
                   error_result_count=None if unknown_error_flags else observed_errors,
                   error_result_count_observed=observed_errors, error_result_unknown_count=unknown_error_flags,
                   error_result_scope='unambiguous paired receipts only; missing receipts or flags stay unknown',
                   repeated_result_blocks=counts['repeated_tool_result_blocks'], missing_receipts=missing_receipts,
                   result_ids_without_observed_call=sum(identity not in calls for identity in results_by_tool),
                   bash_classifications=dict(bash_counts), plugin_invocation_syntax_counts=dict(invocation_counts)),
        bytes_observed=dict(tool_input_compact_json_utf8_bytes_by_name=dict(input_bytes_by_tool),
                            tool_calls_without_input_size=unknown_tool_input_sizes,
                            bash_command_utf8_bytes=bash_command_bytes,
                            read_reported_content_utf8_bytes=read_bytes_known,
                            read_calls_without_content_size=sum(x['reported_content_utf8_bytes'] is None for x in reads),
                            write_input_content_utf8_bytes=write_bytes_known,
                            write_calls_without_content_size=sum(x['input_content_utf8_bytes'] is None for x in writes),
                            json_write_candidate_bytes=dict(json_write_bytes),
                            tool_result_content_utf8_bytes=result_bytes_known,
                            result_blocks_without_content_size=missing_result_content,
                            tool_result_encoding='string UTF8 or compact sorted JSON for structured content; not additional tool_use_result copies',
                            json_candidate_scope='Write inputs only; Bash and other tools may carry JSON, unknown rather than zero total JSON transport'),
        reads=reads, writes=writes,
        anomalies=anomalies, anomaly_count=counts['anomaly_count'],
        malformed_lines=counts['malformed_lines'], oversized_lines=counts['oversized_lines'],
        notice=NOTICE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['summarize'])
    parser.add_argument('events', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = summarize(args.events)
        raw = json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n'
        if args.output:
            if args.output.resolve() == args.events.resolve():
                raise ValueError('output must not replace the input log')
            # The output is optional and explicit; never create project facts/reports.
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(raw)
        else:
            print(raw, end='')
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
