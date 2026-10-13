#!/usr/bin/env python3
"""Inspect unsigned fee caps against a retained ZTO snapshot's block base fee."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
MAX_BYTES = 99000


def load(name, folder, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / 'vendor' / folder / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pinned = load('pinned_fee_snapshot', 'pinned-snapshot', 'pinned_snapshot.py')
fee = load('pinned_fee_arithmetic', 'fee-context', 'fee_context.py')


def unique(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError('duplicate JSON key')
        obj[k] = v
    return obj


def invalid_constant(_):
    raise ValueError('non-finite JSON')


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def parse(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('input must be 1 to 99,000 UTF-8 bytes')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=invalid_constant)


def base_fee(block):
    value = block.get('baseFeePerGas')
    if not isinstance(value, str) or re.fullmatch(r'0x(?:0|[1-9a-f][0-9a-f]{0,63})', value) is None:
        raise ValueError('block requires a canonical lowercase uint256 baseFeePerGas')
    return int(value, 16)


def inspect(obj):
    obj = parse(canonical(obj))  # bound and detach input before validation
    required = {'snapshot', 'transaction', 'input_format'}
    if not isinstance(obj, dict) or not required <= set(obj) or set(obj)-required-{'expected_snapshot_sha256'}:
        raise ValueError('expected snapshot, transaction text and input_format')
    snapshot = obj['snapshot']
    summary = pinned.inspect(snapshot)
    before, after = base_fee(snapshot['block']), base_fee(snapshot['block_after'])
    if before != after:
        raise ValueError('block base fee changed between captured reads')
    digest = hashlib.sha256(canonical(snapshot)).hexdigest()
    if 'expected_snapshot_sha256' in obj:
        expected = obj['expected_snapshot_sha256']
        if not isinstance(expected, str) or re.fullmatch('[0-9a-f]{64}', expected) is None or expected != digest:
            raise ValueError('expected canonical snapshot digest differs')
    diagnostic = fee.inspect(obj['transaction'], before, 1, obj['input_format'])
    diagnostic['context']['source'] = 'Supplied, validated pinned ZTO snapshot; recorded provider block baseFeePerGas, not independently authenticated.'
    result = {
        'schema': 'pinned-fee-context/v1', 'offline': True,
        'snapshot': {'canonical_content_sha256': digest,
                     'expected_digest_matched': 'expected_snapshot_sha256' in obj,
                     'endpoint': snapshot['endpoint'], 'captured_at': snapshot['captured_at'],
                     'block_number': summary['block_number'], 'block_hash': summary['block_hash'],
                     'base_fee_per_gas_wei': str(before),
                     'token': summary['token'], 'total_supply_base_units': summary['total_supply_base_units']},
        'unsigned_input': {'format': obj['input_format'],
                           'text_sha256': hashlib.sha256(obj['transaction'].encode('utf-8')).hexdigest(),
                           'meaning': 'Digest of inspection text, not an Ethereum transaction hash.'},
        'fee_diagnostic': diagnostic,
        'transaction_execution_verified': False,
        'limitations': [
            'Recorded block context only; no freshness, canonicality, finality or provider honesty is independently verified.',
            'A self-computed digest identifies content; an expected digest authenticates it only if separately trusted.',
            'The captured ZTO totalSupply call is not execution of the supplied unsigned message, even if destination and calldata match.',
            'Fee constraints do not establish gas sufficiency, balances, nonce, inclusion, simulation success or safety to sign.',
            'All base-fee arithmetic uses Ethereum EIP-1559 rules; gas is paid in ETH, not ZTO or IMD.',
        ],
    }
    if len(canonical(result)) > MAX_BYTES:
        raise ValueError('report exceeds 99,000 bytes')
    return result


def demo_input():
    return {'snapshot': parse((HERE/'examples/zto-pinned.json').read_bytes()),
            'transaction': fee.reader.D.demo_transaction(), 'input_format': 'rlp'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('demo', 'inspect'))
    args = parser.parse_args(argv)
    try:
        obj = demo_input() if args.command == 'demo' else parse(sys.stdin.buffer.read(MAX_BYTES+1))
        result = inspect(obj)
        if args.command == 'demo':
            result['demo'] = 'Real dated ZTO snapshot plus synthetic unsigned inspection sample; never signed, executed or sent.'
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0 if result['fee_diagnostic']['passesCheckedFeeConstraints'] else 1
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, UnicodeError, RecursionError):
        print('pinned-fee-context: invalid or inconsistent input; no report emitted', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
