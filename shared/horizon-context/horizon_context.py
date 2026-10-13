#!/usr/bin/env python3
"""Bind hypothetical unsigned fee paths to a retained Ethereum block observation."""
import argparse
import json
from pathlib import Path
import sys

import pinned_fee as context

HERE = Path(__file__).resolve().parent
horizon = context.load('horizon_context_model', 'fee-horizon', 'fee_horizon.py')
MAX_BYTES = 99000


def parse(raw):
    # Includes exponent overflow rejection, before any report is emitted.
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('input must be 1 to 99,000 bytes')
    return context.pinned.rpc.strict_json(raw.decode('utf-8'))


def inspect(obj):
    obj = parse(context.canonical(obj))
    required = {'snapshot', 'transaction', 'input_format', 'blocks'}
    if not isinstance(obj, dict) or not required <= set(obj) or set(obj) - required - {'expected_snapshot_sha256'}:
        raise ValueError('expected snapshot, original transaction text, input_format and blocks')
    if type(obj['blocks']) is not int or not 1 <= obj['blocks'] <= horizon.MAX_BLOCKS:
        raise ValueError('blocks must be an integer in 1..64')
    supplied = {key: value for key, value in obj.items() if key != 'blocks'}
    observed = context.inspect(supplied)
    base = int(observed['snapshot']['base_fee_per_gas_wei'])
    # Preserve the native model exactly, including its uint256 input limit.
    modeled = horizon.inspect(obj['transaction'], base, obj['blocks'], obj['input_format'])
    modeled['model']['parentBaseFeeSource'] = (
        'Recorded baseFeePerGas in the validated snapshot, equal before/after; provider claim, not authenticated.'
    )
    result = {
        'schema': 'horizon-context/v1', 'offline': True,
        'snapshot': observed['snapshot'], 'unsigned_input': observed['unsigned_input'],
        'observed_parent_fee_diagnostic': observed['fee_diagnostic'],
        'hypothetical_children': modeled,
        'transaction_execution_verified': False,
        'limitations': observed['limitations'] + [
            'No future block was observed: the first modeled row is the child of the retained parent.',
            'This is a dated provider observation and two stated gas-usage paths, not a forecast or inclusion guarantee.',
            'The twice-target path excludes the extra gas unit possible with an odd block gas limit.',
            'The native model refuses a later step if its preceding hypothetical fee exceeds uint256.',
            'The ZTO supply read is separate evidence; the supplied proposal was never executed by this tool.',
        ],
    }
    if len(context.canonical(result)) > MAX_BYTES:
        raise ValueError('report exceeds 99,000 bytes')
    return result


def demo_input():
    return {'snapshot': parse((HERE / 'examples/zto-pinned.json').read_bytes()),
            'transaction': horizon.fee_context.reader.D.demo_transaction(),
            'input_format': 'rlp', 'blocks': 4}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('demo', 'inspect'))
    args = parser.parse_args(argv)
    try:
        obj = demo_input() if args.command == 'demo' else parse(sys.stdin.buffer.read(MAX_BYTES + 1))
        result = inspect(obj)
        if args.command == 'demo':
            result['demo'] = 'Real dated ZTO snapshot plus synthetic unsigned totalSupply inspection sample; never sent.'
        raw = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError('formatted report exceeds 99,000 bytes')
        print(raw, end='')
        return 1 if result['hypothetical_children']['checkedViolations'] else 0
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, UnicodeError, RecursionError, OverflowError):
        print('horizon-context: invalid, inconsistent or over-limit evidence; no report emitted', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
